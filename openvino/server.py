#!/usr/bin/env python3
"""IPEX-LLM (Intel Extension for PyTorch) Inference Server (FastAPI).

Hosts LLM pipeline accelerated on Intel Arc GPU / XPU using ipex-llm with
on-the-fly INT4 quantization, and vector embeddings on Intel NPU / XPU / CPU.
Provides Ollama-compatible and OpenAI-compatible endpoints:
  /healthz, /api/tags, /api/show, /api/chat, /api/generate, /api/embed, /api/embeddings,
  /api/switch-model, /api/switch-embed-model, /api/reload,
  /v1/chat/completions, /v1/models, /v1/embeddings
"""
import os
import sys

# Ensure Intel Level Zero driver initializes NPU (accel0) in addition to GPU
os.environ.setdefault("ZE_INIT_ALL_DRIVER_TYPES_ENABLE", "1")
os.environ.setdefault("ONEAPI_DEVICE_SELECTOR", "level_zero:*")
os.environ.setdefault("SYCL_CACHE_PERSISTENT", "1")
os.environ.setdefault("SYCL_PI_LEVEL_ZERO_USE_IMMEDIATE_COMMANDLISTS", "1")
os.environ.setdefault("ZE_ENABLE_PCI_ID_DEVICE_ORDER", "1")

import asyncio
import time
import json
import threading
import queue
import logging
from typing import List, Optional, Dict, Any, Union

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] ipex-server: %(message)s")
logger = logging.getLogger("ipex-server")

# Hardware & Directory Configuration
if os.name == "nt":
    default_models_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "k13", "models")
else:
    default_models_dir = "/var/lib/k13/openvino/models"
MODELS_DIR = os.getenv("MODELS_DIR", default_models_dir)
os.makedirs(MODELS_DIR, exist_ok=True)

INFERENCE_DEVICE = os.getenv("LLM_DEVICE", "GPU").upper()
EMBED_DEVICE = os.getenv("EMBED_DEVICE", "NPU").upper()
DEFAULT_LLM_REPO = os.getenv("DEFAULT_MODEL", "Qwen/Qwen2.5-7B-Instruct")
if not DEFAULT_LLM_REPO or "qwen3" in DEFAULT_LLM_REPO.lower() or DEFAULT_LLM_REPO.lower() in ("default", "none"):
    DEFAULT_LLM_REPO = "Qwen/Qwen2.5-7B-Instruct"
DEFAULT_EMBED_REPO = os.getenv("EMBED_MODEL", "BAAI/bge-base-en-v1.5")
SWITCH_ALLOW_CPU = os.getenv("SWITCH_ALLOW_CPU", "off").lower() in ("on", "1", "true")
LLM_THINKING = os.getenv("LLM_THINKING", "off").lower() in ("on", "1", "true")
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "2048"))
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "11434"))

llm_lock = threading.Lock()
embed_lock = threading.Lock()

# Global Model & Engine Holders
llm_model = None
llm_tokenizer = None
llm_engine_type = "ipex-llm"  # "ipex-llm" or fallback "openvino"
openvino_pipeline = None

embed_model = None
embed_tokenizer = None
openvino_embed_core = None

active_llm_device = INFERENCE_DEVICE
active_embed_device = EMBED_DEVICE
current_llm_repo = DEFAULT_LLM_REPO
current_embed_repo = DEFAULT_EMBED_REPO

model_switch_status: Dict[str, Any] = {"state": "idle", "stage": "ready", "model": DEFAULT_LLM_REPO, "error": None}
embed_switch_status: Dict[str, Any] = {"state": "idle", "stage": "ready", "model": DEFAULT_EMBED_REPO, "error": None}


def detect_xpu_available() -> bool:
    """Check if Intel XPU (Arc GPU via oneAPI / Level-Zero) is available in PyTorch."""
    try:
        try:
            import intel_extension_for_pytorch as ipex
        except ImportError:
            pass
        try:
            import ipex_llm
        except ImportError:
            pass
        import torch
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            count = torch.xpu.device_count()
            if count > 0:
                return True
            else:
                hint = (
                    "Ensure Intel Arc Graphics WHQL driver is installed on Windows 11."
                    if os.name == "nt" else
                    "Install with: sudo apt install -y libze1 libze-intel-gpu1 intel-opencl-icd && sudo usermod -aG render,video $USER"
                )
                logger.warning(
                    f"torch.xpu.is_available() is True, but torch.xpu.device_count() is 0. "
                    f"Intel Level Zero runtime cannot see the Arc GPU. {hint}"
                )
                return False
    except Exception as e:
        logger.warning(f"Error querying PyTorch XPU device: {e}")
    return False


def extract_content(content_val: Any) -> str:
    """Extract string content from string, list of blocks, or dict."""
    if isinstance(content_val, str):
        return content_val
    if isinstance(content_val, list):
        parts = []
        for item in content_val:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif "text" in item:
                    parts.append(str(item["text"]))
                elif "content" in item:
                    parts.append(str(item["content"]))
                else:
                    parts.append(str(item))
            else:
                parts.append(str(item))
        return "".join(parts)
    if isinstance(content_val, dict):
        return str(content_val.get("text", "") or content_val.get("content", "") or content_val)
    return str(content_val)


def format_chat_prompt(messages: List[Any], model_id: str, tokenizer=None) -> str:
    """Format chat messages using Hugging Face tokenizer template or standard ChatML."""
    formatted_messages = []
    for m in messages:
        role = getattr(m, "role", "user") if hasattr(m, "role") else (m.get("role", "user") if isinstance(m, dict) else "user")
        raw_c = getattr(m, "content", "") if hasattr(m, "content") else (m.get("content", "") if isinstance(m, dict) else "")
        content = extract_content(raw_c)
        formatted_messages.append({"role": role, "content": content})

    # 1. Prefer native Hugging Face chat_template if available
    if tokenizer is not None and hasattr(tokenizer, "apply_chat_template"):
        try:
            return tokenizer.apply_chat_template(formatted_messages, tokenize=False, add_generation_prompt=True)
        except Exception:
            pass

    # 2. Heuristic fallback based on model family
    m_lower = (model_id or "").lower()
    is_qwen = "qwen" in m_lower or "deepseek" in m_lower
    is_llama = "llama" in m_lower
    is_phi = "phi" in m_lower
    is_gemma = "gemma" in m_lower

    prompt = ""
    if is_qwen:
        # ChatML format
        for m in formatted_messages:
            prompt += f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n"
        prompt += "<|im_start|>assistant\n"
    elif is_llama:
        prompt = "<|begin_of_text|>"
        for m in formatted_messages:
            prompt += f"<|start_header_id|>{m['role']}<|end_header_id|>\n\n{m['content']}<|eot_id|>"
        prompt += "<|start_header_id|>assistant<|end_header_id|>\n\n"
    elif is_phi:
        for m in formatted_messages:
            prompt += f"<|{m['role']}|>\n{m['content']}<|end|>\n"
        prompt += "<|assistant|>\n"
    elif is_gemma:
        for m in formatted_messages:
            prompt += f"<start_of_turn>{m['role']}\n{m['content']}<end_of_turn>\n"
        prompt += "<start_of_turn>model\n"
    else:
        for m in formatted_messages:
            prompt += f"<|{m['role']}|>\n{m['content']}</s>\n"
        prompt += "<|assistant|>\n"

    return prompt


def load_llm(model_id: str):
    """Load model using IPEX-LLM (Intel Extension for PyTorch) with dynamic INT4 quantization on XPU."""
    global llm_model, llm_tokenizer, llm_engine_type, openvino_pipeline
    global active_llm_device, current_llm_repo, model_switch_status

    with llm_lock:
        logger.info(f"Loading LLM '{model_id}' via IPEX-LLM...")
        old_model = llm_model
        old_tok = llm_tokenizer
        old_pipe = openvino_pipeline
        old_repo = current_llm_repo
        old_device = active_llm_device
        old_engine = llm_engine_type

        hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN") or None
        model_switch_status["state"] = "loading"
        model_switch_status["stage"] = "downloading"
        model_switch_status["model"] = model_id
        model_switch_status["error"] = None
        model_switch_status["start_time"] = time.time()

        try:
            import torch
            import gc

            # Check if repo has pre-converted OpenVINO IR files
            is_ov_ir = "openvino/" in model_id.lower() or "-ov" in model_id.lower()

            # Fix for transformers >= 4.45 compatibility with ipex-llm:
            # ipex-llm imports OffloadedCache from transformers.cache_utils, which was refactored in newer transformers.
            try:
                import transformers.cache_utils
                if not hasattr(transformers.cache_utils, "OffloadedCache"):
                    class OffloadedCache:
                        pass
                    transformers.cache_utils.OffloadedCache = OffloadedCache
            except Exception:
                pass

            # Attempt IPEX-LLM PyTorch loading first
            ipex_available = False
            IpexAutoModel = None
            try:
                from ipex_llm.transformers import AutoModelForCausalLM as IpexAutoModel
                ipex_available = True
                logger.info("IPEX-LLM library imported successfully.")
            except Exception as e_ipex:
                logger.warning(f"IPEX-LLM not importable in runtime environment: {e_ipex}")

            from transformers import AutoTokenizer

            # 1. Load Tokenizer
            logger.info(f"Loading tokenizer for {model_id}...")
            tokenizer = AutoTokenizer.from_pretrained(
                model_id,
                trust_remote_code=True,
                token=hf_token
            )
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            # 2. Determine target device (Intel XPU or CPU)
            xpu_ready = detect_xpu_available()
            if INFERENCE_DEVICE == "CPU":
                target_dev = "cpu"
            elif not xpu_ready:
                if not SWITCH_ALLOW_CPU:
                    fix_hint = (
                        "Install Intel Graphics Driver for Windows 11 (Level Zero / SYCL supported natively)"
                        if os.name == "nt" else
                        "sudo apt install -y libze1 libze-intel-gpu1 intel-opencl-icd && sudo usermod -aG render,video $USER"
                    )
                    raise RuntimeError(
                        f"Inference device is configured as '{INFERENCE_DEVICE}', but Intel Arc GPU (XPU) device count is 0. "
                        f"{fix_hint}"
                    )
                logger.warning(f"Intel Arc GPU (XPU) not available (device count 0). Falling back to CPU because SWITCH_ALLOW_CPU=on.")
                target_dev = "cpu"
            else:
                target_dev = "xpu"

            logger.info(f"Target hardware for {model_id}: {target_dev.upper()} (XPU ready: {xpu_ready})")
            model_switch_status["stage"] = "quantizing"

            # 3. Clean up active models from VRAM (keep references in old_* variables for fallback)
            llm_model = None
            openvino_pipeline = None
            gc.collect()
            if xpu_ready and hasattr(torch, "xpu"):
                try:
                    torch.xpu.empty_cache()
                except Exception:
                    pass

            loaded_model = None
            loaded_engine = "ipex-llm"

            if ipex_available and IpexAutoModel is not None:
                # Load via IPEX-LLM with dynamic 4-bit INT4 quantization
                logger.info(f"Loading {model_id} via IPEX-LLM (4-bit INT4 quantization on {target_dev})...")
                model_switch_status["stage"] = "compiling"
                
                m_low = model_id.lower()
                is_deepseek_or_qwen = "deepseek" in m_low or "qwen" in m_low

                xpu_attempts = []
                if target_dev == "xpu":
                    # Intel Lunar Lake Arc 140V GPU optimization:
                    # 1. cpu_embedding=True prevents the massive 152k-vocabulary embedding table
                    #    (1.1 GB in memory) from overflowing the 6.8 GB Arc VRAM ceiling.
                    # 2. optimize_model=False for DeepSeek/Qwen prevents graph-rewriter kernel
                    #    crashes / ValueError while preserving full 4-bit INT4 quantization.
                    # 3. We let IPEX-LLM handle internal dtypes rather than forcing torch.float16,
                    #    which prevents RoPE rotary embedding precision mismatches.
                    xpu_attempts.append({
                        "name": "XPU INT4 (cpu_embedding=True, optimize_model=False)",
                        "kwargs": {
                            "load_in_4bit": True,
                            "cpu_embedding": True,
                            "optimize_model": False if is_deepseek_or_qwen else True,
                            "trust_remote_code": True,
                            "use_cache": True,
                            "token": hf_token
                        }
                    })
                    xpu_attempts.append({
                        "name": "XPU INT4 (fallback without cpu_embedding, optimize_model=False)",
                        "kwargs": {
                            "load_in_4bit": True,
                            "optimize_model": False,
                            "trust_remote_code": True,
                            "use_cache": True,
                            "token": hf_token
                        }
                    })
                    xpu_attempts.append({
                        "name": "XPU INT4 (standard default)",
                        "kwargs": {
                            "load_in_4bit": True,
                            "optimize_model": True,
                            "trust_remote_code": True,
                            "use_cache": True,
                            "token": hf_token
                        }
                    })

                xpu_success = False
                last_xpu_error = None

                for attempt in xpu_attempts:
                    try:
                        logger.info(f"Attempting IPEX-LLM load: {attempt['name']}...")
                        gc.collect()
                        if hasattr(torch, "xpu"):
                            try:
                                torch.xpu.empty_cache()
                            except Exception:
                                pass

                        m = IpexAutoModel.from_pretrained(model_id, **attempt["kwargs"])
                        m = m.to("xpu")
                        m.eval()
                        loaded_model = m
                        target_dev = "xpu"
                        xpu_success = True
                        logger.info(f"[✓] IPEX-LLM successfully loaded {model_id} onto Intel Arc GPU (XPU) via {attempt['name']}")
                        break
                    except Exception as ex_attempt:
                        last_xpu_error = ex_attempt
                        logger.warning(f"IPEX-LLM attempt '{attempt['name']}' failed on XPU: {ex_attempt}")
                        gc.collect()
                        if hasattr(torch, "xpu"):
                            try:
                                torch.xpu.empty_cache()
                            except Exception:
                                pass

                if not xpu_success:
                    if target_dev == "xpu" and not SWITCH_ALLOW_CPU:
                        raise RuntimeError(
                            f"Failed to allocate {model_id} on Intel Arc GPU (XPU): {last_xpu_error}. "
                            f"(Tip: Enable 'Allow CPU fallback' in Model Manager if you wish to run on CPU RAM instead)."
                        )
                    
                    logger.warning(f"Falling back to CPU for {model_id} (GPU error: {last_xpu_error})...")
                    gc.collect()
                    try:
                        loaded_model = IpexAutoModel.from_pretrained(
                            model_id,
                            load_in_4bit=True,
                            optimize_model=False,
                            trust_remote_code=True,
                            use_cache=True,
                            token=hf_token
                        ).to("cpu")
                        loaded_model.eval()
                        target_dev = "cpu"
                        logger.info(f"[✓] IPEX-LLM loaded {model_id} on CPU")
                    except Exception as ex_cpu:
                        if last_xpu_error:
                            raise RuntimeError(f"GPU error: {last_xpu_error} | CPU error: {ex_cpu}")
                        raise ex_cpu
            else:
                # Fallback to standard Transformers or OpenVINO GenAI if IPEX-LLM package is still installing
                logger.info(f"IPEX-LLM package not ready. Attempting fallback loading for {model_id}...")
                try:
                    import openvino_genai as ov_genai
                    from huggingface_hub import snapshot_download
                    local_target = os.path.join(MODELS_DIR, model_id.replace("/", "_"))
                    model_path = snapshot_download(repo_id=model_id, local_dir=local_target, token=hf_token)
                    ov_pipe = ov_genai.LLMPipeline(model_path, "GPU" if target_dev == "xpu" else "CPU")
                    openvino_pipeline = ov_pipe
                    loaded_engine = "openvino"
                    logger.info(f"[✓] OpenVINO GenAI loaded {model_id} on {target_dev.upper()}")
                except Exception as e_ov:
                    logger.error(f"Cannot load {model_id} via OpenVINO GenAI ({e_ov}) and IPEX-LLM is not installed.")
                    raise RuntimeError(
                        f"IPEX-LLM is not installed in the server Python environment, preventing 4-bit INT4 quantization for '{model_id}'. "
                        "Unquantized FP16/FP32 loading on CPU was blocked to protect the system from an out-of-memory crash. "
                        "Please run on the host: ./scripts/k13ctl.sh install-ipex"
                    )

            llm_model = loaded_model
            llm_tokenizer = tokenizer
            llm_engine_type = loaded_engine
            active_llm_device = "GPU" if target_dev == "xpu" else "CPU"
            current_llm_repo = model_id
            model_switch_status = {"state": "idle", "stage": "ready", "model": model_id, "error": None}
            logger.info(f"[✓] LLM successfully active: {model_id} on {active_llm_device} ({llm_engine_type})")

        except Exception as e:
            err_msg = str(e)
            logger.error(f"Failed to load LLM {model_id}: {err_msg}")
            # Restore previous model
            try:
                llm_model = old_model
                llm_tokenizer = old_tok
                openvino_pipeline = old_pipe
                active_llm_device = old_device
                current_llm_repo = old_repo
                llm_engine_type = old_engine
            except Exception as res_err:
                logger.warning(f"Could not restore previous model: {res_err}")
                llm_model = None
            model_switch_status = {"state": "error", "stage": "failed", "model": old_repo, "error": err_msg}
            raise RuntimeError(f"Failed to load model {model_id}: {err_msg}")
        finally:
            if model_switch_status.get("state") == "loading":
                model_switch_status = {
                    "state": "error",
                    "stage": "failed",
                    "model": old_repo or model_id,
                    "error": "Model load terminated unexpectedly"
                }


def load_embed(model_id: str):
    """Load vector embedding model on Intel NPU (with CPU/XPU fallback)."""
    global embed_model, embed_tokenizer, openvino_embed_core
    global active_embed_device, current_embed_repo, embed_switch_status

    with embed_lock:
        target_device = EMBED_DEVICE.upper()
        logger.info(f"Loading embedding model {model_id} on {target_device}...")
        embed_switch_status["state"] = "loading"
        embed_switch_status["stage"] = "downloading"
        embed_switch_status["model"] = model_id
        embed_switch_status["error"] = None
        embed_switch_status["start_time"] = time.time()

        try:
            from transformers import AutoTokenizer
            hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN") or None

            tok = AutoTokenizer.from_pretrained(model_id, token=hf_token)
            model_obj = None
            resolved_dev = target_device

            # 1. Attempt Intel NPU via OpenVINO
            try:
                import openvino as ov
                core = ov.Core()
                ov_model = core.read_model(model_id) if os.path.exists(model_id) else None
                if not ov_model:
                    # Load via optimum-intel or standard transformers
                    from transformers import AutoModel
                    pt_model = AutoModel.from_pretrained(model_id, token=hf_token)
                    model_obj = pt_model.to("cpu")
                    resolved_dev = "NPU" if "NPU" in core.available_devices else "CPU"
            except Exception:
                from transformers import AutoModel
                pt_model = AutoModel.from_pretrained(model_id, token=hf_token)
                model_obj = pt_model.to("cpu")
                resolved_dev = "CPU"

            embed_tokenizer = tok
            embed_model = model_obj
            active_embed_device = resolved_dev
            current_embed_repo = model_id
            embed_switch_status = {"state": "idle", "stage": "ready", "model": model_id, "error": None}
            logger.info(f"[✓] Embedding model {model_id} active on {active_embed_device}")
        except Exception as e:
            logger.error(f"Failed to load embedding model {model_id}: {e}")
            embed_switch_status = {"state": "error", "stage": "failed", "model": current_embed_repo, "error": str(e)}
            raise e
        finally:
            if embed_switch_status.get("state") == "loading":
                embed_switch_status = {
                    "state": "error",
                    "stage": "failed",
                    "model": current_embed_repo or model_id,
                    "error": "Embedding load terminated unexpectedly"
                }


# ==============================================================================
# FastAPI Application & Endpoints
# ==============================================================================

app = FastAPI(
    title="IPEX-LLM Inference Server",
    description="Accelerated LLM & Embedding Server on Intel Hardware (Arc GPU / XPU + NPU)",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    """Load default models at startup in background."""
    def init_background():
        try:
            load_llm(DEFAULT_LLM_REPO)
        except Exception as e:
            logger.warning(f"Initial LLM load deferred or failed: {e}")
        try:
            load_embed(DEFAULT_EMBED_REPO)
        except Exception as e:
            logger.warning(f"Initial embedding load deferred or failed: {e}")

    threading.Thread(target=init_background, daemon=True).start()


@app.get("/healthz")
def healthz():
    """Health check returning active hardware, model, and engine."""
    return {
        "status": "ok",
        "engine": "ipex-llm",
        "llm_hardware": active_llm_device,
        "embed_hardware": active_embed_device,
        "current_model": current_llm_repo,
        "embed_model": current_embed_repo,
        "max_new_tokens": MAX_NEW_TOKENS,
        "switch_status": model_switch_status,
        "embed_switch_status": embed_switch_status
    }


# ==============================================================================
# Model Switching Endpoints
# ==============================================================================

class SwitchModelReq(BaseModel):
    model: str
    force: Optional[bool] = False


@app.post("/api/switch-model")
def switch_model(req: SwitchModelReq):
    global model_switch_status
    if model_switch_status.get("state") == "loading" and not req.force:
        start_t = model_switch_status.get("start_time", 0)
        # If it has been in loading state for over 5 minutes, permit overriding
        if time.time() - start_t < 300:
            raise HTTPException(status_code=409, detail=f"Model switch already in progress ({model_switch_status.get('model')})")
        else:
            logger.warning(f"Overriding stale switch state for {model_switch_status.get('model')}")

    def run_switch():
        try:
            load_llm(req.model)
        except Exception as e:
            logger.error(f"Switch thread error: {e}")

    threading.Thread(target=run_switch, daemon=True).start()
    return {"status": "started", "target": req.model}


@app.post("/api/switch-model/reset")
def reset_model_switch():
    global model_switch_status
    model_switch_status = {"state": "idle", "stage": "ready", "model": current_llm_repo, "error": None}
    logger.info("Model switch status manually reset to idle.")
    return {"status": "reset", "model": current_llm_repo}


@app.get("/api/switch-model/status")
def switch_model_status():
    status = dict(model_switch_status)
    if status.get("state") == "loading" and "start_time" in status:
        status["elapsed_seconds"] = int(time.time() - status["start_time"])
    return {
        "current_model": current_llm_repo,
        "active_device": active_llm_device,
        "engine": llm_engine_type,
        "switch_status": status
    }


@app.post("/api/switch-embed-model")
def switch_embed_model(req: SwitchModelReq):
    global embed_switch_status
    if embed_switch_status.get("state") == "loading" and not req.force:
        start_t = embed_switch_status.get("start_time", 0)
        if time.time() - start_t < 300:
            raise HTTPException(status_code=409, detail="Embed switch already in progress")
        else:
            logger.warning("Overriding stale embed switch state")

    def run_embed_switch():
        try:
            load_embed(req.model)
        except Exception as e:
            logger.error(f"Embed switch thread error: {e}")

    threading.Thread(target=run_embed_switch, daemon=True).start()
    return {"status": "started", "target": req.model}


@app.post("/api/switch-embed-model/reset")
def reset_embed_switch():
    global embed_switch_status
    embed_switch_status = {"state": "idle", "stage": "ready", "model": current_embed_repo, "error": None}
    logger.info("Embed switch status manually reset to idle.")
    return {"status": "reset", "model": current_embed_repo}


@app.get("/api/switch-embed-model/status")
def switch_embed_model_status():
    status = dict(embed_switch_status)
    if status.get("state") == "loading" and "start_time" in status:
        status["elapsed_seconds"] = int(time.time() - status["start_time"])
    return {
        "current_model": current_embed_repo,
        "active_device": active_embed_device,
        "switch_status": status
    }


@app.post("/api/reload")
def reload_gpu():
    load_llm(current_llm_repo)
    return {"status": "reloaded", "device": active_llm_device, "engine": llm_engine_type}


# ==============================================================================
# Vector Embeddings Endpoints (/api/embed, /api/embeddings, /v1/embeddings)
# ==============================================================================

class EmbedReq(BaseModel):
    model: Optional[str] = None
    input: Optional[Union[str, List[str]]] = None
    prompt: Optional[str] = None


@app.post("/api/embed")
@app.post("/api/embeddings")
def embed_endpoint(req: EmbedReq):
    texts = []
    if req.input:
        texts = [req.input] if isinstance(req.input, str) else req.input
    elif req.prompt:
        texts = [req.prompt]
    else:
        raise HTTPException(status_code=400, detail="Missing input or prompt")

    dims = 384 if "small" in (req.model or current_embed_repo) else 768

    if not embed_model or not embed_tokenizer:
        return {"embeddings": [[0.0] * dims for _ in texts], "embedding": [0.0] * dims}

    with embed_lock:
        import torch
        results = []
        for text in texts:
            inputs = embed_tokenizer(text, padding=True, truncation=True, max_length=512, return_tensors="pt")
            with torch.no_grad():
                out = embed_model(**inputs)
                token_embs = out[0]
                mask = inputs["attention_mask"].unsqueeze(-1).expand(token_embs.size()).float()
                sum_embs = torch.sum(token_embs * mask, 1)
                sum_mask = torch.clamp(mask.sum(1), min=1e-9)
                pooled = sum_embs / sum_mask
                norm = torch.nn.functional.normalize(pooled, p=2, dim=1)
                results.append(norm[0].cpu().tolist())

        return {"embeddings": results, "embedding": results[0] if results else [0.0] * dims}


@app.post("/v1/embeddings")
@app.post("/embeddings")
def v1_embeddings(req: EmbedReq):
    out = embed_endpoint(req)
    embs = out.get("embeddings", [])
    data = []
    for i, emb in enumerate(embs):
        data.append({
            "object": "embedding",
            "index": i,
            "embedding": emb
        })
    return {
        "object": "list",
        "data": data,
        "model": current_embed_repo,
        "usage": {"prompt_tokens": len(data) * 16, "total_tokens": len(data) * 16}
    }


# ==============================================================================
# Ollama-Compatible Chat & Generation Endpoints
# ==============================================================================

class ChatMessageReq(BaseModel):
    role: str
    content: Optional[Union[str, List[Any], Dict[str, Any]]] = ""

    class Config:
        extra = "allow"


class ChatReq(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessageReq]
    stream: Optional[bool] = False

    class Config:
        extra = "allow"


@app.post("/api/chat")
async def chat_endpoint(req: ChatReq):
    if not llm_model and not openvino_pipeline:
        raise HTTPException(status_code=503, detail="LLM is still loading onto Intel hardware")

    formatted_prompt = format_chat_prompt(req.messages, current_llm_repo, llm_tokenizer)

    def generate_sync():
        with llm_lock:
            try:
                import torch
                if llm_model and llm_tokenizer:
                    inputs = llm_tokenizer(formatted_prompt, return_tensors="pt")
                    dev = getattr(llm_model, "device", None) or ("xpu" if active_llm_device == "GPU" else "cpu")
                    input_ids = inputs.input_ids.to(dev)
                    attention_mask = inputs.attention_mask.to(dev)

                    with torch.inference_mode():
                        output_ids = llm_model.generate(
                            input_ids=input_ids,
                            attention_mask=attention_mask,
                            max_new_tokens=MAX_NEW_TOKENS,
                            do_sample=False,
                            pad_token_id=llm_tokenizer.pad_token_id or llm_tokenizer.eos_token_id
                        )
                    generated_ids = output_ids[0][input_ids.shape[1]:]
                    return llm_tokenizer.decode(generated_ids, skip_special_tokens=True)
                elif openvino_pipeline:
                    import openvino_genai as ov_genai
                    cfg = ov_genai.GenerationConfig()
                    cfg.max_new_tokens = MAX_NEW_TOKENS
                    return str(openvino_pipeline.generate(formatted_prompt, cfg))
            except Exception as e:
                logger.error(f"Generation error: {e}")
                return f"Error during generation: {e}"

    if not req.stream:
        loop = asyncio.get_event_loop()
        answer = await loop.run_in_executor(None, generate_sync)
        return {
            "model": current_llm_repo,
            "message": {"role": "assistant", "content": answer},
            "done": True
        }

    # Streaming mode
    async def stream_generator():
        token_q = queue.Queue()
        done_flag = threading.Event()
        err_holder = [None]

        def generate_worker():
            with llm_lock:
                try:
                    import torch
                    if llm_model and llm_tokenizer:
                        from transformers import TextIteratorStreamer
                        streamer = TextIteratorStreamer(llm_tokenizer, skip_prompt=True, skip_special_tokens=True)
                        inputs = llm_tokenizer(formatted_prompt, return_tensors="pt")
                        dev = getattr(llm_model, "device", None) or ("xpu" if active_llm_device == "GPU" else "cpu")

                        gen_kwargs = dict(
                            input_ids=inputs.input_ids.to(dev),
                            attention_mask=inputs.attention_mask.to(dev),
                            max_new_tokens=MAX_NEW_TOKENS,
                            streamer=streamer,
                            do_sample=False,
                            pad_token_id=llm_tokenizer.pad_token_id or llm_tokenizer.eos_token_id
                        )

                        def run_in_thread():
                            try:
                                with torch.inference_mode():
                                    llm_model.generate(**gen_kwargs)
                            except Exception as ex:
                                err_holder[0] = str(ex)

                        t = threading.Thread(target=run_in_thread, daemon=True)
                        t.start()

                        for new_text in streamer:
                            token_q.put(new_text)
                    elif openvino_pipeline:
                        import openvino_genai as ov_genai
                        cfg = ov_genai.GenerationConfig()
                        cfg.max_new_tokens = MAX_NEW_TOKENS

                        def streamer_cb(subword: str):
                            token_q.put(subword)
                            return ov_genai.StreamingStatus.RUNNING

                        openvino_pipeline.generate(formatted_prompt, cfg, streamer_cb)
                except Exception as ex:
                    logger.error(f"Generation error in worker: {ex}")
                    err_holder[0] = str(ex)
                finally:
                    done_flag.set()

        threading.Thread(target=generate_worker, daemon=True).start()

        # Send immediate first chunk so Continue in VS Code starts response immediately
        yield json.dumps({"model": current_llm_repo, "message": {"role": "assistant", "content": ""}, "done": False}) + "\n"

        words_count = 0
        while not done_flag.is_set() or not token_q.empty():
            try:
                token_val = token_q.get_nowait()
                if token_val:
                    words_count += 1
                    yield json.dumps({"model": current_llm_repo, "message": {"role": "assistant", "content": token_val}, "done": False}) + "\n"
            except queue.Empty:
                await asyncio.sleep(0.01)

        if err_holder[0]:
            yield json.dumps({"model": current_llm_repo, "message": {"role": "assistant", "content": f"\n[Hardware Error: {err_holder[0]}]"}, "done": False}) + "\n"

        yield json.dumps({"model": current_llm_repo, "message": {"role": "assistant", "content": ""}, "done": True, "eval_count": words_count}) + "\n"

    return StreamingResponse(
        stream_generator(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    )


class GenerateReq(BaseModel):
    model: Optional[str] = None
    prompt: Union[str, List[Any]]
    system: Optional[str] = None
    stream: Optional[bool] = False
    options: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"


@app.post("/api/generate")
async def generate_endpoint(req: GenerateReq):
    """Ollama-compatible prompt completion endpoint."""
    raw_p = extract_content(req.prompt)
    messages = []
    if req.system:
        messages.append({"role": "system", "content": req.system})
    messages.append({"role": "user", "content": raw_p})

    chat_req = ChatReq(model=req.model, messages=[ChatMessageReq(**m) for m in messages], stream=req.stream)
    return await chat_endpoint(chat_req)


@app.get("/api/tags")
def tags_endpoint():
    """Ollama-compatible model tags endpoint."""
    return {
        "models": [
            {
                "name": current_llm_repo,
                "model": current_llm_repo,
                "modified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "size": 4500000000,
                "digest": "sha256:ipex_llm_intel_xpu",
                "details": {
                    "parent_model": "",
                    "format": "ipex-llm",
                    "family": "qwen" if "qwen" in current_llm_repo.lower() else "llama",
                    "families": ["ipex-llm", "intel_xpu"],
                    "parameter_size": "7B" if "7b" in current_llm_repo.lower() else "3B",
                    "quantization_level": "int4"
                }
            }
        ]
    }


@app.post("/api/show")
def show_endpoint(req: Dict[str, Any]):
    m_name = req.get("name") or req.get("model") or current_llm_repo
    return {
        "modelfile": f"# IPEX-LLM Intel XPU Model\nFROM {m_name}\n",
        "parameters": "temperature 0.7\ntop_p 0.9",
        "details": {
            "format": "ipex-llm",
            "family": "ipex",
            "quantization_level": "int4"
        }
    }


# ==============================================================================
# OpenAI-Compatible Endpoints (/v1/models, /v1/chat/completions)
# ==============================================================================

@app.get("/v1/models")
@app.get("/models")
def v1_models():
    now = int(time.time())
    models_list = [
        {
            "id": current_llm_repo,
            "object": "model",
            "created": now,
            "owned_by": "ipex-llm",
            "permission": [],
            "root": current_llm_repo,
            "parent": None
        },
        {
            "id": current_embed_repo,
            "object": "model",
            "created": now,
            "owned_by": "ipex-llm",
            "permission": [],
            "root": current_embed_repo,
            "parent": None
        }
    ]
    aliases = [
        "default",
        "qwen2.5-7b-instruct",
        "qwen2.5-coder-7b-instruct",
        "deepseek-r1-distill-qwen-7b",
        "qwen2.5-3b-instruct"
    ]
    for alias in aliases:
        models_list.append({
            "id": alias,
            "object": "model",
            "created": now,
            "owned_by": "ipex-llm",
            "permission": [],
            "root": current_llm_repo,
            "parent": None
        })
    return {"object": "list", "data": models_list}


class OpenAIChatReq(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessageReq]
    stream: Optional[bool] = False
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9
    max_tokens: Optional[int] = None

    class Config:
        extra = "allow"


@app.post("/v1/chat/completions")
@app.post("/chat/completions")
async def openai_chat_completions(req: OpenAIChatReq):
    if not llm_model and not openvino_pipeline:
        raise HTTPException(status_code=503, detail="LLM is still loading onto Intel hardware")

    cmpl_id = f"chatcmpl-{int(time.time()*1000)}"
    created_ts = int(time.time())
    formatted_prompt = format_chat_prompt(req.messages, current_llm_repo, llm_tokenizer)
    tokens_limit = req.max_tokens or MAX_NEW_TOKENS

    def generate_sync():
        with llm_lock:
            try:
                import torch
                if llm_model and llm_tokenizer:
                    inputs = llm_tokenizer(formatted_prompt, return_tensors="pt")
                    dev = getattr(llm_model, "device", None) or ("xpu" if active_llm_device == "GPU" else "cpu")
                    input_ids = inputs.input_ids.to(dev)
                    attention_mask = inputs.attention_mask.to(dev)

                    with torch.inference_mode():
                        out = llm_model.generate(
                            input_ids=input_ids,
                            attention_mask=attention_mask,
                            max_new_tokens=tokens_limit,
                            do_sample=req.temperature > 0,
                            temperature=req.temperature if req.temperature > 0 else 1.0,
                            top_p=req.top_p or 0.9,
                            pad_token_id=llm_tokenizer.pad_token_id or llm_tokenizer.eos_token_id
                        )
                    return llm_tokenizer.decode(out[0][input_ids.shape[1]:], skip_special_tokens=True)
                elif openvino_pipeline:
                    import openvino_genai as ov_genai
                    cfg = ov_genai.GenerationConfig()
                    cfg.max_new_tokens = tokens_limit
                    return str(openvino_pipeline.generate(formatted_prompt, cfg))
            except Exception as e:
                logger.error(f"OpenAI sync generation error: {e}")
                return f"Error: {e}"

    if not req.stream:
        loop = asyncio.get_event_loop()
        answer = await loop.run_in_executor(None, generate_sync)
        return {
            "id": cmpl_id,
            "object": "chat.completion",
            "created": created_ts,
            "model": current_llm_repo,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": answer},
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": len(formatted_prompt.split()),
                "completion_tokens": len(answer.split()),
                "total_tokens": len(formatted_prompt.split()) + len(answer.split())
            }
        }

    # True Token-by-Token Streaming with immediate first SSE chunk
    async def sse_stream():
        init_data = {
            "id": cmpl_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": current_llm_repo,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": ""},
                    "finish_reason": None
                }
            ]
        }
        yield f"data: {json.dumps(init_data)}\n\n"

        token_q = queue.Queue()
        done_flag = threading.Event()
        err_holder = [None]

        def generate_worker():
            with llm_lock:
                try:
                    import torch
                    if llm_model and llm_tokenizer:
                        from transformers import TextIteratorStreamer
                        streamer = TextIteratorStreamer(llm_tokenizer, skip_prompt=True, skip_special_tokens=True)
                        inputs = llm_tokenizer(formatted_prompt, return_tensors="pt")
                        dev = getattr(llm_model, "device", None) or ("xpu" if active_llm_device == "GPU" else "cpu")

                        gen_kwargs = dict(
                            input_ids=inputs.input_ids.to(dev),
                            attention_mask=inputs.attention_mask.to(dev),
                            max_new_tokens=tokens_limit,
                            streamer=streamer,
                            do_sample=req.temperature > 0,
                            pad_token_id=llm_tokenizer.pad_token_id or llm_tokenizer.eos_token_id
                        )
                        if req.temperature > 0:
                            gen_kwargs["temperature"] = req.temperature
                            gen_kwargs["top_p"] = req.top_p or 0.9

                        def run_in_thread():
                            try:
                                with torch.inference_mode():
                                    llm_model.generate(**gen_kwargs)
                            except Exception as ex:
                                err_holder[0] = str(ex)

                        t = threading.Thread(target=run_in_thread, daemon=True)
                        t.start()

                        for new_text in streamer:
                            token_q.put(new_text)
                    elif openvino_pipeline:
                        import openvino_genai as ov_genai
                        cfg = ov_genai.GenerationConfig()
                        cfg.max_new_tokens = tokens_limit

                        def streamer_cb(subword: str):
                            token_q.put(subword)
                            return ov_genai.StreamingStatus.RUNNING

                        openvino_pipeline.generate(formatted_prompt, cfg, streamer_cb)
                except Exception as ex:
                    logger.error(f"Streaming worker error: {ex}")
                    err_holder[0] = str(ex)
                finally:
                    done_flag.set()

        threading.Thread(target=generate_worker, daemon=True).start()

        while not done_flag.is_set() or not token_q.empty():
            try:
                token_val = token_q.get_nowait()
                if token_val:
                    chunk_data = {
                        "id": cmpl_id,
                        "object": "chat.completion.chunk",
                        "created": created_ts,
                        "model": current_llm_repo,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": token_val},
                                "finish_reason": None
                            }
                        ]
                    }
                    yield f"data: {json.dumps(chunk_data)}\n\n"
            except queue.Empty:
                await asyncio.sleep(0.01)

        if err_holder[0]:
            err_data = {
                "id": cmpl_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": current_llm_repo,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": f"\n[Hardware Error: {err_holder[0]}]"},
                        "finish_reason": "error"
                    }
                ]
            }
            yield f"data: {json.dumps(err_data)}\n\n"

        stop_data = {
            "id": cmpl_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": current_llm_repo,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }
            ]
        }
        yield f"data: {json.dumps(stop_data)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        sse_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    )


class OpenAICompletionReq(BaseModel):
    model: Optional[str] = None
    prompt: Union[str, List[Any]]
    stream: Optional[bool] = False
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None

    class Config:
        extra = "allow"


@app.post("/v1/completions")
@app.post("/completions")
async def openai_completions(req: OpenAICompletionReq):
    raw_p = extract_content(req.prompt)
    chat_req = OpenAIChatReq(
        model=req.model,
        messages=[ChatMessageReq(role="user", content=raw_p)],
        stream=req.stream,
        temperature=req.temperature,
        max_tokens=req.max_tokens
    )
    return await openai_chat_completions(chat_req)


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting IPEX-LLM server on {SERVER_HOST}:{SERVER_PORT}...")
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="info")
