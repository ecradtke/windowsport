#!/usr/bin/env python3
"""llama.cpp Inference & Embedding Server (FastAPI) for Windows.

Manages a native Windows `llama-server.exe` (llama.cpp) subprocess for GGUF LLM
inference with GPU layer offloading (-ngl) and dynamic Hugging Face GGUF model
switching, plus Hugging Face vector embeddings (BAAI/bge-base-en-v1.5 768d default).

Provides Ollama-compatible and OpenAI-compatible endpoints on port 11434:
  /healthz, /api/tags, /api/show, /api/chat, /api/generate, /api/embed, /api/embeddings,
  /api/switch-model, /api/switch-embed-model, /api/reload,
  /v1/chat/completions, /v1/completions, /v1/models, /v1/embeddings
"""
import os
import sys
import glob
import time
import json
import shutil
import signal
import atexit
import asyncio
import logging
import threading
import subprocess
from typing import List, Optional, Dict, Any, Union, Tuple

import requests
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] llama-server: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("llama-server")

# Directory & Runtime Configuration
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
default_models_dir = os.path.join(BASE_DIR, "data", "models")
MODELS_DIR = os.getenv("LLAMA_MODELS_DIR") or os.getenv("MODELS_DIR") or default_models_dir
os.makedirs(MODELS_DIR, exist_ok=True)

INFERENCE_DEVICE = os.getenv("LLM_DEVICE", "GPU").upper()
# Always target Intel NPU for vector embeddings so GPU remains 100% dedicated to llama.cpp LLMs
EMBED_DEVICE = "NPU"

DEFAULT_LLM_REPO = os.getenv("DEFAULT_MODEL", "Qwen/Qwen2.5-7B-Instruct-GGUF")
if not DEFAULT_LLM_REPO or DEFAULT_LLM_REPO.lower() in ("default", "none"):
    DEFAULT_LLM_REPO = "Qwen/Qwen2.5-7B-Instruct-GGUF"

DEFAULT_EMBED_REPO = os.getenv("EMBED_MODEL", "BAAI/bge-base-en-v1.5")
SWITCH_ALLOW_CPU = os.getenv("SWITCH_ALLOW_CPU", "on").lower() in ("on", "1", "true")
LLM_THINKING = os.getenv("LLM_THINKING", "off").lower() in ("on", "1", "true")
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "2048"))
LLAMA_NGL = int(os.getenv("LLAMA_NGL", "99"))
LLAMA_CTX_SIZE = int(os.getenv("LLAMA_CTX_SIZE", "16384"))
SERVER_HOST = os.getenv("LLAMA_HOST") or os.getenv("SERVER_HOST") or "0.0.0.0"
SERVER_PORT = int(os.getenv("LLAMA_PORT") or os.getenv("SERVER_PORT") or "11434")
INTERNAL_LLAMA_PORT = int(os.getenv("LLAMA_INTERNAL_PORT", str(SERVER_PORT + 1)))
INTERNAL_EMBED_PORT = int(os.getenv("LLAMA_EMBED_PORT", str(SERVER_PORT + 2)))

llm_lock = threading.Lock()
embed_lock = threading.Lock()

# Process & Model State
llama_proc: Optional[subprocess.Popen] = None
embed_proc: Optional[subprocess.Popen] = None
current_gguf_path: Optional[str] = None
current_embed_gguf_path: Optional[str] = None
active_llm_device = INFERENCE_DEVICE
active_embed_device = EMBED_DEVICE
current_llm_repo = DEFAULT_LLM_REPO
current_embed_repo = DEFAULT_EMBED_REPO

embed_model = None
embed_tokenizer = None
embed_input_names: List[str] = []

model_switch_status: Dict[str, Any] = {"state": "idle", "stage": "ready", "model": DEFAULT_LLM_REPO, "error": None}
embed_switch_status: Dict[str, Any] = {"state": "idle", "stage": "ready", "model": DEFAULT_EMBED_REPO, "error": None}

# Mapping from standard HF repo IDs to official/community GGUF repos for convenience
KNOWN_GGUF_REPOS: Dict[str, str] = {
    "baai/bge-base-en-v1.5": "CompendiumLabs/bge-base-en-v1.5-gguf",
    "baai/bge-small-en-v1.5": "CompendiumLabs/bge-small-en-v1.5-gguf",
    "nomic-ai/nomic-embed-text-v1.5": "nomic-ai/nomic-embed-text-v1.5-GGUF",
    "qwen/qwen2.5-7b-instruct": "Qwen/Qwen2.5-7B-Instruct-GGUF",
    "qwen/qwen2.5-3b-instruct": "Qwen/Qwen2.5-3B-Instruct-GGUF",
    "qwen/qwen2.5-14b-instruct": "Qwen/Qwen2.5-14B-Instruct-GGUF",
    "qwen/qwen2.5-coder-7b-instruct": "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF",
    "qwen/qwen2.5-coder-3b-instruct": "Qwen/Qwen2.5-Coder-3B-Instruct-GGUF",
    "qwen/qwen3-8b": "Qwen/Qwen3-8B-GGUF",
    "qwen/qwen3-4b": "Qwen/Qwen3-4B-GGUF",
    "deepseek-ai/deepseek-r1-distill-qwen-7b": "bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF",
    "deepseek-ai/deepseek-r1-distill-qwen-1.5b": "bartowski/DeepSeek-R1-Distill-Qwen-1.5B-GGUF",
    "microsoft/phi-3.5-mini-instruct": "bartowski/Phi-3.5-mini-instruct-GGUF",
    "microsoft/phi-4": "bartowski/phi-4-GGUF",
    "google/gemma-2-2b-it": "bartowski/gemma-2-2b-it-GGUF",
    "google/gemma-2-9b-it": "bartowski/gemma-2-9b-it-GGUF",
    "google/gemma-3-4b-it": "bartowski/google_gemma-3-4b-it-GGUF",
    "google/gemma-3-12b-it": "bartowski/google_gemma-3-12b-it-GGUF",
    "meta-llama/llama-3.2-3b-instruct": "bartowski/Llama-3.2-3B-Instruct-GGUF",
    "meta-llama/llama-3.1-8b-instruct": "bartowski/Meta-Llama-3.1-8B-Instruct-GGUF",
    "mistralai/mistral-7b-instruct-v0.3": "bartowski/Mistral-7B-Instruct-v0.3-GGUF",
    "bigcode/starcoder2-3b": "second-state/StarCoder2-3B-GGUF",
}

PREFERRED_QUANTS = [
    "q4_k_m",
    "q4_k_s",
    "q4_0",
    "iq4_xs",
    "q5_k_m",
    "q5_k_s",
    "q6_k",
    "q8_0",
    "f16",
    "f32",
]


def find_llama_server_binary() -> Optional[str]:
    """Locate llama-server.exe on Windows."""
    # 1. Explicit env var
    env_bin = os.getenv("LLAMA_SERVER_BIN", "").strip().strip('"')
    if env_bin and os.path.isfile(env_bin):
        return env_bin

    env_dir = os.getenv("LLAMA_CPP_DIR", "").strip().strip('"')
    if env_dir and os.path.isdir(env_dir):
        for rel in (
            "llama-server.exe",
            os.path.join("bin", "llama-server.exe"),
            os.path.join("build", "bin", "Release", "llama-server.exe"),
            os.path.join("build", "bin", "llama-server.exe"),
        ):
            cand = os.path.join(env_dir, rel)
            if os.path.isfile(cand):
                return cand

    # 2. System PATH
    which_bin = shutil.which("llama-server.exe") or shutil.which("llama-server")
    if which_bin:
        return which_bin

    # 3. Project bin\llama\llama-server.exe and common Windows install paths
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    user_profile = os.environ.get("USERPROFILE", "")
    program_files = os.environ.get("ProgramFiles", "C:\\Program Files")

    search_patterns = [
        os.path.join(BASE_DIR, "bin", "llama", "llama-server.exe"),
        os.path.join(BASE_DIR, "bin", "llama", "*", "llama-server.exe"),
        os.path.join(local_app_data, "Microsoft", "WinGet", "Packages", "*llama*", "**", "llama-server.exe"),
        os.path.join(local_app_data, "Programs", "llama.cpp", "llama-server.exe"),
        os.path.join(user_profile, "llama.cpp", "**", "llama-server.exe"),
        os.path.join(user_profile, "scoop", "apps", "llama.cpp", "current", "llama-server.exe"),
        os.path.join(program_files, "llama.cpp", "**", "llama-server.exe"),
        "C:\\llama.cpp\\llama-server.exe",
        "C:\\llama.cpp\\build\\bin\\Release\\llama-server.exe",
        "C:\\storage\\llama.cpp\\**\\llama-server.exe",
    ]
    for pattern in search_patterns:
        if "*" in pattern:
            matches = glob.glob(pattern, recursive=True)
            if matches:
                return matches[0]
        elif os.path.isfile(pattern):
            return pattern

    return None


def resolve_gguf_file(model_id: str) -> Tuple[str, str]:
    """Resolve a model_id (local path, GGUF HF repo, or standard HF repo) to a local .gguf file.
    Returns (resolved_repo_id, local_gguf_path).
    """
    clean_id = model_id.strip()

    # 1. Direct local .gguf file path
    if os.path.isfile(clean_id) and clean_id.lower().endswith(".gguf"):
        return clean_id, os.path.abspath(clean_id)

    local_in_models = os.path.join(MODELS_DIR, clean_id)
    if os.path.isfile(local_in_models) and local_in_models.lower().endswith(".gguf"):
        return clean_id, os.path.abspath(local_in_models)

    # 2. Check optional :quant suffix (e.g. Qwen/Qwen3-8B-GGUF:Q4_K_M)
    requested_quant = None
    if ":" in clean_id and not os.path.drive.splitdrive(clean_id)[0]:
        clean_id, requested_quant = clean_id.split(":", 1)
        requested_quant = requested_quant.strip().lower()

    # 3. Map standard HF repo ID to known GGUF repo if needed
    repo_id = KNOWN_GGUF_REPOS.get(clean_id.lower(), clean_id)

    hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN") or None
    from huggingface_hub import HfApi, hf_hub_download

    api = HfApi(token=hf_token)

    def find_gguf_in_repo(target_repo: str) -> List[str]:
        files = api.list_repo_files(repo_id=target_repo, repo_type="model")
        # Exclude split shards like *-00001-of-00002.gguf or mmproj vision projectors
        return [
            f for f in files
            if f.lower().endswith(".gguf")
            and "mmproj" not in f.lower()
            and "-of-" not in f.lower()
        ]

    gguf_files: List[str] = []
    try:
        gguf_files = find_gguf_in_repo(repo_id)
    except Exception as e:
        logger.warning(f"Could not list files in {repo_id}: {e}")

    # 4. If the repo didn't have .gguf files, search Hugging Face Hub for a matching GGUF repo
    if not gguf_files:
        base_name = repo_id.split("/")[-1]
        candidates = [
            f"{repo_id}-GGUF",
            f"bartowski/{base_name}-GGUF",
            f"unsloth/{base_name}-GGUF",
            f"Qwen/{base_name}-GGUF",
        ]
        for cand in candidates:
            try:
                gguf_files = find_gguf_in_repo(cand)
                if gguf_files:
                    logger.info(f"Resolved '{model_id}' to Hugging Face GGUF repository '{cand}'")
                    repo_id = cand
                    break
            except Exception:
                continue

    if not gguf_files:
        try:
            search_term = f"{repo_id.split('/')[-1]} GGUF"
            models = list(api.list_models(search=search_term, limit=5))
            for m in models:
                if "gguf" in m.id.lower():
                    try:
                        gguf_files = find_gguf_in_repo(m.id)
                        if gguf_files:
                            logger.info(f"Auto-discovered GGUF repository '{m.id}' for '{model_id}'")
                            repo_id = m.id
                            break
                    except Exception:
                        continue
        except Exception:
            pass

    if not gguf_files:
        raise RuntimeError(
            f"No single-file .gguf weights found for '{model_id}'. "
            f"Please specify a Hugging Face GGUF repository (e.g. 'Qwen/Qwen2.5-7B-Instruct-GGUF' or 'bartowski/Qwen3-8B-GGUF')."
        )

    # 5. Select the best quantization file
    chosen_file = None
    if requested_quant:
        for f in gguf_files:
            if requested_quant in f.lower():
                chosen_file = f
                break

    if not chosen_file:
        for q in PREFERRED_QUANTS:
            for f in gguf_files:
                if q in f.lower():
                    chosen_file = f
                    break
            if chosen_file:
                break

    if not chosen_file:
        chosen_file = gguf_files[0]

    logger.info(f"Downloading / verifying GGUF file '{chosen_file}' from '{repo_id}' into {MODELS_DIR}...")
    local_path = hf_hub_download(
        repo_id=repo_id,
        filename=chosen_file,
        local_dir= os.path.join(MODELS_DIR, repo_id.replace("/", "__")),
        token=hf_token,
    )
    return repo_id, local_path


def stop_llama_process():
    """Stop the running llama-server.exe subprocess cleanly."""
    global llama_proc
    if llama_proc is not None:
        try:
            if llama_proc.poll() is None:
                logger.info(f"Stopping llama-server.exe subprocess (PID {llama_proc.pid})...")
                llama_proc.terminate()
                try:
                    llama_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    llama_proc.kill()
        except Exception as e:
            logger.warning(f"Error stopping llama-server.exe: {e}")
        finally:
            llama_proc = None


def stop_embed_process():
    """Stop the running embedding llama-server.exe subprocess cleanly."""
    global embed_proc
    if embed_proc is not None:
        try:
            if embed_proc.poll() is None:
                logger.info(f"Stopping embedding llama-server.exe subprocess (PID {embed_proc.pid})...")
                embed_proc.terminate()
                try:
                    embed_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    embed_proc.kill()
        except Exception as e:
            logger.warning(f"Error stopping embedding llama-server.exe: {e}")
        finally:
            embed_proc = None


atexit.register(stop_llama_process)
atexit.register(stop_embed_process)


def start_llama_subprocess(gguf_path: str, ngl: int) -> subprocess.Popen:
    """Spawn llama-server.exe and wait until its /health endpoint reports ok."""
    bin_path = find_llama_server_binary()
    if not bin_path:
        raise RuntimeError(
            "llama-server.exe not found! Ensure llama.cpp is in your PATH, "
            "or set LLAMA_SERVER_BIN / LLAMA_CPP_DIR in your .env file."
        )

    bin_dir = os.path.dirname(os.path.abspath(bin_path))
    cmd = [
        bin_path,
        "-m", gguf_path,
        "--host", "127.0.0.1",
        "--port", str(INTERNAL_LLAMA_PORT),
        "-ngl", str(ngl),
        "-c", str(LLAMA_CTX_SIZE),
    ]

    logger.info(f"Launching llama.cpp server: {' '.join(cmd)}")
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.Popen(
        cmd,
        cwd=bin_dir or BASE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creation_flags,
    )

    # Stream child stdout in a background daemon thread so pipes never block
    recent_lines: List[str] = []

    def _log_reader(p: subprocess.Popen):
        try:
            if p.stdout:
                for line in p.stdout:
                    s = line.rstrip()
                    if s:
                        recent_lines.append(s)
                        if len(recent_lines) > 40:
                            recent_lines.pop(0)
                        logger.info(f"[llama.cpp] {s}")
        except Exception:
            pass

    threading.Thread(target=_log_reader, args=(proc,), daemon=True).start()

    # Poll /health until ready (up to 180 seconds for large GGUFs)
    health_url = f"http://127.0.0.1:{INTERNAL_LLAMA_PORT}/health"
    deadline = time.time() + 180
    while time.time() < deadline:
        if proc.poll() is not None:
            tail = "\n".join(recent_lines[-10:])
            raise RuntimeError(f"llama-server.exe exited early (code {proc.returncode}). Log tail:\n{tail}")
        try:
            r = requests.get(health_url, timeout=2)
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "ok":
                    return proc
        except Exception:
            pass
        time.sleep(0.5)

    proc.terminate()
    raise RuntimeError("Timed out waiting for llama-server.exe to load GGUF model.")


def load_llm(model_id: str):
    """Download/resolve GGUF model and start llama-server.exe with GPU offload."""
    global llama_proc, current_gguf_path, active_llm_device, current_llm_repo, model_switch_status

    with llm_lock:
        logger.info(f"Loading LLM '{model_id}' via llama.cpp...")
        old_repo = current_llm_repo
        old_gguf = current_gguf_path
        old_device = active_llm_device

        model_switch_status = {
            "state": "loading",
            "stage": "downloading",
            "model": model_id,
            "error": None,
            "start_time": time.time(),
        }

        try:
            resolved_repo, gguf_path = resolve_gguf_file(model_id)
            model_switch_status["stage"] = "compiling"

            stop_llama_process()

            want_gpu = INFERENCE_DEVICE != "CPU" and LLAMA_NGL > 0
            target_ngl = LLAMA_NGL if want_gpu else 0

            try:
                proc = start_llama_subprocess(gguf_path, ngl=target_ngl)
                llama_proc = proc
                active_llm_device = "GPU" if target_ngl > 0 else "CPU"
            except Exception as gpu_err:
                if target_ngl > 0 and SWITCH_ALLOW_CPU:
                    logger.warning(f"GPU offload (-ngl {target_ngl}) failed ({gpu_err}); retrying on CPU (-ngl 0)...")
                    proc = start_llama_subprocess(gguf_path, ngl=0)
                    llama_proc = proc
                    active_llm_device = "CPU"
                else:
                    raise gpu_err

            current_gguf_path = gguf_path
            current_llm_repo = model_id
            model_switch_status = {"state": "idle", "stage": "ready", "model": model_id, "error": None}
            logger.info(f"[✓] llama.cpp active: {model_id} ({os.path.basename(gguf_path)}) on {active_llm_device}")

        except Exception as e:
            err_msg = str(e)
            logger.error(f"Failed to load LLM '{model_id}': {err_msg}")
            # Rollback to previous GGUF if available
            if old_gguf and os.path.isfile(old_gguf) and (llama_proc is None or llama_proc.poll() is not None):
                try:
                    logger.info(f"Rolling back to previous model: {old_repo} ({old_gguf})")
                    ngl = LLAMA_NGL if old_device == "GPU" else 0
                    llama_proc = start_llama_subprocess(old_gguf, ngl=ngl)
                    current_gguf_path = old_gguf
                    current_llm_repo = old_repo
                    active_llm_device = old_device
                except Exception as rb_err:
                    logger.warning(f"Rollback failed: {rb_err}")
            model_switch_status = {"state": "error", "stage": "failed", "model": old_repo, "error": err_msg}
            raise RuntimeError(err_msg)


def start_embed_subprocess(gguf_path: str, ngl: int) -> subprocess.Popen:
    """Spawn llama-server.exe in --embeddings mode on INTERNAL_EMBED_PORT."""
    bin_path = find_llama_server_binary()
    if not bin_path:
        raise RuntimeError(
            "llama-server.exe not found! Ensure llama.cpp is in your PATH, "
            "or set LLAMA_SERVER_BIN / LLAMA_CPP_DIR in your .env file."
        )

    bin_dir = os.path.dirname(os.path.abspath(bin_path))
    cmd = [
        bin_path,
        "-m", gguf_path,
        "--host", "127.0.0.1",
        "--port", str(INTERNAL_EMBED_PORT),
        "--embeddings",
        "-ngl", str(ngl),
        "-c", "2048",
        "-b", "2048",
        "-ub", "2048",
    ]

    logger.info(f"Launching llama.cpp embedding server: {' '.join(cmd)}")
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.Popen(
        cmd,
        cwd=bin_dir or BASE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creation_flags,
    )

    recent_lines: List[str] = []

    def _embed_log_reader(p: subprocess.Popen):
        try:
            if p.stdout:
                for line in p.stdout:
                    s = line.rstrip()
                    if s:
                        recent_lines.append(s)
                        if len(recent_lines) > 30:
                            recent_lines.pop(0)
        except Exception:
            pass

    threading.Thread(target=_embed_log_reader, args=(proc,), daemon=True).start()

    health_url = f"http://127.0.0.1:{INTERNAL_EMBED_PORT}/health"
    deadline = time.time() + 90
    while time.time() < deadline:
        if proc.poll() is not None:
            tail = "\n".join(recent_lines[-10:])
            raise RuntimeError(f"Embedding llama-server.exe exited early (code {proc.returncode}). Log tail:\n{tail}")
        try:
            r = requests.get(health_url, timeout=2)
            if r.status_code == 200 and r.json().get("status") == "ok":
                return proc
        except Exception:
            pass
        time.sleep(0.5)

    proc.terminate()
    raise RuntimeError("Timed out waiting for embedding llama-server.exe to start.")


def _resolve_onnx_embed_repo(model_id: str) -> str:
    """Ensure embedding repo points to the canonical HF repo containing tokenizer.json & onnx/model.onnx."""
    clean = model_id.strip()
    low = clean.lower()
    if "bge-small" in low:
        return "BAAI/bge-small-en-v1.5"
    if "bge-base" in low or "bge" in low:
        return "BAAI/bge-base-en-v1.5"
    return clean


def load_embed(model_id: str):
    """Load vector embedding model (e.g. BAAI/bge-base-en-v1.5 768d) onto the Intel NPU."""
    global embed_proc, current_embed_gguf_path, embed_model, embed_tokenizer, embed_input_names, active_embed_device, current_embed_repo, embed_switch_status

    with embed_lock:
        target_repo = _resolve_onnx_embed_repo(model_id)
        logger.info(f"Loading embedding model '{target_repo}' onto Intel NPU...")
        embed_switch_status = {
            "state": "loading",
            "stage": "downloading",
            "model": target_repo,
            "error": None,
            "start_time": time.time(),
        }
        try:
            stop_embed_process()
            hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN") or None
            from huggingface_hub import hf_hub_download
            from tokenizers import Tokenizer
            import openvino as ov

            local_repo_dir = os.path.join(MODELS_DIR, target_repo.replace("/", "__"))
            os.makedirs(local_repo_dir, exist_ok=True)

            tok_path = hf_hub_download(
                repo_id=target_repo,
                filename="tokenizer.json",
                local_dir=local_repo_dir,
                token=hf_token,
            )
            try:
                onnx_path = hf_hub_download(
                    repo_id=target_repo,
                    filename="onnx/model.onnx",
                    local_dir=local_repo_dir,
                    token=hf_token,
                )
            except Exception:
                onnx_path = hf_hub_download(
                    repo_id=target_repo,
                    filename="model.onnx",
                    local_dir=local_repo_dir,
                    token=hf_token,
                )

            embed_switch_status["stage"] = "compiling"

            tok = Tokenizer.from_file(tok_path)
            tok.enable_truncation(max_length=512)
            tok.enable_padding(length=512, pad_id=0, pad_token="[PAD]")

            core = ov.Core()
            npu_cache_dir = os.path.join(MODELS_DIR, "npu_cache")
            os.makedirs(npu_cache_dir, exist_ok=True)
            try:
                core.set_property({"CACHE_DIR": npu_cache_dir})
            except Exception:
                pass

            avail = core.available_devices
            logger.info(f"Available accelerator devices for embeddings: {avail}")
            if "NPU" not in avail:
                raise RuntimeError(
                    f"Intel NPU device not found in available devices ({avail}). "
                    "Verify the Intel AI Boost NPU driver is enabled in Windows Device Manager."
                )

            ov_model = core.read_model(onnx_path)
            shapes = {}
            inp_names: List[str] = []
            for inp in ov_model.inputs:
                name = inp.get_any_name()
                inp_names.append(name)
                shapes[name] = [1, 512]
            ov_model.reshape(shapes)

            compiled = core.compile_model(ov_model, "NPU")

            embed_tokenizer = tok
            embed_model = compiled
            embed_input_names = inp_names
            active_embed_device = "NPU"
            current_embed_repo = target_repo
            embed_switch_status = {"state": "idle", "stage": "ready", "model": target_repo, "error": None}
            logger.info(f"[✓] Embedding model '{target_repo}' compiled and active on Intel NPU (static [1, 512])")
        except Exception as e:
            logger.error(f"Failed to load embedding model '{model_id}' on Intel NPU: {e}")
            embed_switch_status = {"state": "error", "stage": "failed", "model": current_embed_repo, "error": str(e)}
            raise e


# ==============================================================================
# FastAPI Application & Endpoints
# ==============================================================================

app = FastAPI(
    title="K13 llama.cpp Inference Server",
    description="Native Windows llama.cpp GGUF Server + Hugging Face Vector Embeddings",
    version="3.0.0",
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
    def init_background():
        try:
            load_embed(DEFAULT_EMBED_REPO)
        except Exception as e:
            logger.warning(f"Initial embedding load deferred or failed: {e}")
        try:
            load_llm(DEFAULT_LLM_REPO)
        except Exception as e:
            logger.warning(f"Initial LLM load deferred or failed: {e}")

    threading.Thread(target=init_background, daemon=True).start()


@app.on_event("shutdown")
def shutdown_event():
    stop_llama_process()
    stop_embed_process()


@app.get("/healthz")
def healthz():
    llama_alive = llama_proc is not None and llama_proc.poll() is None
    return {
        "status": "ok",
        "engine": "llama.cpp",
        "llama_server_binary": find_llama_server_binary(),
        "llama_process_running": llama_alive,
        "llm_hardware": active_llm_device,
        "embed_hardware": active_embed_device,
        "current_model": current_llm_repo,
        "current_gguf": os.path.basename(current_gguf_path) if current_gguf_path else None,
        "embed_model": current_embed_repo,
        "max_new_tokens": MAX_NEW_TOKENS,
        "switch_status": model_switch_status,
        "embed_switch_status": embed_switch_status,
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
        if time.time() - start_t < 300:
            raise HTTPException(status_code=409, detail=f"Model switch already in progress ({model_switch_status.get('model')})")

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
    return {"status": "reset", "model": current_llm_repo}


@app.get("/api/switch-model/status")
def switch_model_status():
    status = dict(model_switch_status)
    if status.get("state") == "loading" and "start_time" in status:
        status["elapsed_seconds"] = int(time.time() - status["start_time"])
    return {
        "current_model": current_llm_repo,
        "active_device": active_llm_device,
        "engine": "llama.cpp",
        "switch_status": status,
    }


@app.post("/api/switch-embed-model")
def switch_embed_model(req: SwitchModelReq):
    global embed_switch_status
    if embed_switch_status.get("state") == "loading" and not req.force:
        start_t = embed_switch_status.get("start_time", 0)
        if time.time() - start_t < 300:
            raise HTTPException(status_code=409, detail="Embed switch already in progress")

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
    return {"status": "reset", "model": current_embed_repo}


@app.get("/api/switch-embed-model/status")
def switch_embed_model_status():
    status = dict(embed_switch_status)
    if status.get("state") == "loading" and "start_time" in status:
        status["elapsed_seconds"] = int(time.time() - status["start_time"])
    return {
        "current_model": current_embed_repo,
        "active_device": active_embed_device,
        "switch_status": status,
    }


@app.post("/api/reload")
def reload_gpu():
    load_llm(current_llm_repo)
    return {"status": "reloaded", "device": active_llm_device, "engine": "llama.cpp"}


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
    texts: List[str] = []
    if req.input:
        texts = [req.input] if isinstance(req.input, str) else req.input
    elif req.prompt:
        texts = [req.prompt]
    else:
        raise HTTPException(status_code=400, detail="Missing input or prompt")

    dims = 384 if "small" in (req.model or current_embed_repo).lower() else 768

    if embed_model is None or embed_tokenizer is None:
        try:
            load_embed(req.model or current_embed_repo)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Intel NPU embedding model not ready: {e}")

    with embed_lock:
        results: List[List[float]] = []
        for text in texts:
            enc = embed_tokenizer.encode(text or "")
            ids = np.array([enc.ids], dtype=np.int64)
            mask = np.array([enc.attention_mask], dtype=np.int64)
            type_ids = np.array([enc.type_ids], dtype=np.int64)

            feed: Dict[str, np.ndarray] = {}
            for name in embed_input_names:
                if "input_ids" in name:
                    feed[name] = ids
                elif "attention_mask" in name:
                    feed[name] = mask
                elif "token_type_ids" in name:
                    feed[name] = type_ids
                else:
                    feed[name] = ids

            ov_out = embed_model(feed)
            token_embs = np.array(list(ov_out.values())[0], dtype=np.float32)

            # Mean pooling with attention mask + L2 normalization
            mask_exp = np.expand_dims(mask, axis=-1).astype(np.float32)
            sum_embs = np.sum(token_embs * mask_exp, axis=1)
            sum_mask = np.clip(np.sum(mask_exp, axis=1), a_min=1e-9, a_max=None)
            pooled = (sum_embs / sum_mask)[0]
            norm_val = float(np.linalg.norm(pooled))
            if norm_val > 1e-9:
                pooled = pooled / norm_val
            results.append(pooled.tolist())

        return {"embeddings": results, "embedding": results[0] if results else [0.0] * dims}


@app.post("/v1/embeddings")
@app.post("/embeddings")
def v1_embeddings(req: EmbedReq):
    out = embed_endpoint(req)
    embs = out.get("embeddings", [])
    data = [{"object": "embedding", "index": i, "embedding": emb} for i, emb in enumerate(embs)]
    return {
        "object": "list",
        "data": data,
        "model": current_embed_repo,
        "usage": {"prompt_tokens": len(data) * 16, "total_tokens": len(data) * 16},
    }


# ==============================================================================
# Chat & Completion Endpoints (Proxying to llama-server.exe)
# ==============================================================================

def extract_content(content_val: Any) -> str:
    if isinstance(content_val, str):
        return content_val
    if isinstance(content_val, list):
        parts = []
        for item in content_val:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or item))
            else:
                parts.append(str(item))
        return "".join(parts)
    if isinstance(content_val, dict):
        return str(content_val.get("text") or content_val.get("content") or content_val)
    return str(content_val or "")


class ChatMessageReq(BaseModel):
    role: str
    content: Optional[Union[str, List[Any], Dict[str, Any]]] = ""

    class Config:
        extra = "allow"


class ChatReq(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessageReq]
    stream: Optional[bool] = False
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None

    class Config:
        extra = "allow"


def _ensure_llama_ready():
    if llama_proc is None or llama_proc.poll() is not None:
        if model_switch_status.get("state") == "loading":
            raise HTTPException(
                status_code=503,
                detail=f"llama.cpp is currently loading '{model_switch_status.get('model')}' ({model_switch_status.get('stage')})",
            )
        raise HTTPException(
            status_code=503,
            detail="llama-server.exe is not running. Check .\\scripts\\windows\\k13ctl.ps1 status or switch models in Model Manager.",
        )


@app.post("/api/chat")
async def chat_endpoint(req: ChatReq):
    _ensure_llama_ready()
    llama_url = f"http://127.0.0.1:{INTERNAL_LLAMA_PORT}/v1/chat/completions"
    formatted_msgs = [{"role": m.role, "content": extract_content(m.content)} for m in req.messages]
    payload = {
        "messages": formatted_msgs,
        "stream": bool(req.stream),
        "max_tokens": req.max_tokens or MAX_NEW_TOKENS,
        "temperature": req.temperature if req.temperature is not None else 0.7,
    }

    if not req.stream:
        def _sync_call():
            r = requests.post(llama_url, json=payload, timeout=300)
            r.raise_for_status()
            return r.json()

        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, _sync_call)
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        return {
            "model": current_llm_repo,
            "message": {"role": "assistant", "content": content},
            "done": True,
            "eval_count": usage.get("completion_tokens", 0),
            "prompt_eval_count": usage.get("prompt_tokens", 0),
        }

    async def ndjson_stream():
        # Send immediate initial chunk
        yield json.dumps({"model": current_llm_repo, "message": {"role": "assistant", "content": ""}, "done": False}) + "\n"
        token_count = 0
        try:
            with requests.post(llama_url, json=payload, stream=True, timeout=300) as r:
                r.raise_for_status()
                for raw_line in r.iter_lines(decode_unicode=True):
                    if not raw_line:
                        continue
                    line = raw_line.strip()
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        piece = delta.get("content") or delta.get("reasoning_content") or ""
                        if piece:
                            token_count += 1
                            yield json.dumps({
                                "model": current_llm_repo,
                                "message": {"role": "assistant", "content": piece},
                                "done": False,
                            }) + "\n"
                    except Exception:
                        pass
                    await asyncio.sleep(0)
        except Exception as e:
            logger.error(f"llama.cpp stream error: {e}")
            yield json.dumps({
                "model": current_llm_repo,
                "message": {"role": "assistant", "content": f"\n[llama.cpp error: {e}]"},
                "done": False,
            }) + "\n"

        yield json.dumps({
            "model": current_llm_repo,
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "eval_count": token_count,
        }) + "\n"

    return StreamingResponse(
        ndjson_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
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
    raw_p = extract_content(req.prompt)
    messages = []
    if req.system:
        messages.append(ChatMessageReq(role="system", content=req.system))
    messages.append(ChatMessageReq(role="user", content=raw_p))

    chat_req = ChatReq(model=req.model, messages=messages, stream=req.stream)
    res = await chat_endpoint(chat_req)
    if isinstance(res, dict):
        res["response"] = res.get("message", {}).get("content", "")
    return res


@app.get("/api/tags")
def tags_endpoint():
    return {
        "models": [
            {
                "name": current_llm_repo,
                "model": current_llm_repo,
                "modified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "size": os.path.getsize(current_gguf_path) if (current_gguf_path and os.path.isfile(current_gguf_path)) else 4500000000,
                "digest": "sha256:llamacpp_gguf",
                "details": {
                    "parent_model": "",
                    "format": "gguf",
                    "family": "llama",
                    "families": ["llama", "gguf"],
                    "parameter_size": "7B",
                    "quantization_level": "Q4_K_M",
                },
            }
        ]
    }


@app.post("/api/show")
def show_endpoint(req: Dict[str, Any]):
    m_name = req.get("name") or req.get("model") or current_llm_repo
    return {
        "modelfile": f"# llama.cpp GGUF Model\nFROM {m_name}\n",
        "parameters": "temperature 0.7\ntop_p 0.9",
        "details": {"format": "gguf", "family": "llama", "quantization_level": "Q4_K_M"},
    }


# ==============================================================================
# OpenAI-Compatible Endpoints (/v1/models, /v1/chat/completions, /v1/completions)
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
            "owned_by": "llama.cpp",
            "permission": [],
            "root": current_llm_repo,
            "parent": None,
        },
        {
            "id": current_embed_repo,
            "object": "model",
            "created": now,
            "owned_by": "llama.cpp",
            "permission": [],
            "root": current_embed_repo,
            "parent": None,
        },
    ]
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
    _ensure_llama_ready()
    llama_url = f"http://127.0.0.1:{INTERNAL_LLAMA_PORT}/v1/chat/completions"
    formatted_msgs = [{"role": m.role, "content": extract_content(m.content)} for m in req.messages]
    payload = {
        "model": req.model or current_llm_repo,
        "messages": formatted_msgs,
        "stream": bool(req.stream),
        "temperature": req.temperature if req.temperature is not None else 0.7,
        "top_p": req.top_p or 0.9,
        "max_tokens": req.max_tokens or MAX_NEW_TOKENS,
    }

    if not req.stream:
        def _sync_call():
            r = requests.post(llama_url, json=payload, timeout=300)
            r.raise_for_status()
            return r.json()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_call)

    async def sse_stream():
        try:
            with requests.post(llama_url, json=payload, stream=True, timeout=300) as r:
                r.raise_for_status()
                for raw_line in r.iter_lines(decode_unicode=True):
                    if raw_line:
                        yield f"{raw_line}\n\n"
                        await asyncio.sleep(0)
        except Exception as e:
            err_chunk = {
                "id": f"chatcmpl-{int(time.time()*1000)}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": current_llm_repo,
                "choices": [{"index": 0, "delta": {"content": f"\n[llama.cpp error: {e}]"}, "finish_reason": "error"}],
            }
            yield f"data: {json.dumps(err_chunk)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        sse_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
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
        max_tokens=req.max_tokens,
    )
    return await openai_chat_completions(chat_req)


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting K13 llama.cpp orchestrator server on {SERVER_HOST}:{SERVER_PORT}...")
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="info")

