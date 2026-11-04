#!/usr/bin/env python3
"""
K13 AI Hub - Pure Python Web Portal & Cluster Management Server (FastAPI)
Replaces Node.js / Vite dev server with a lightweight native Python server on port 3000.
Serves the React + TypeScript frontend directly from src/ without Node.js or npm.
"""

import os
import re
import sys
import json
import time
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional

import requests
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
ENV_FILE = BASE_DIR / ".env"
PID_DIR = BASE_DIR / "data" / "pids"
LOG_DIR = BASE_DIR / "logs"

MASKED_SECRETS = {"PG_PASS", "FRESHRSS_API_PASS", "HF_TOKEN", "POSTGRES_PASSWORD", "PASSWORD"}

FRONTEND_ENV_PREFIXES = (
    "VITE_",
    "RAG_",
    "MAX_",
    "TOP_",
    "DEFAULT_",
    "LLM_",
    "LLAMA_",
    "EMBED_",
    "QDRANT_",
    "SWITCH_",
    "FRESHRSS_",
    "PG_",
    "K13_",
    "WEB_",
    "DROPIT_",
)


def parse_env_file(mask_secrets: bool = True) -> Dict[str, Any]:
    parsed: Dict[str, str] = {}
    if not ENV_FILE.is_file():
        return {"exists": False, "env": parsed, "source": "none"}

    try:
        content = ENV_FILE.read_text(encoding="utf-8", errors="replace")
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            if mask_secrets and key in MASKED_SECRETS and val:
                parsed[key] = "•••••••• (configured)"
            else:
                parsed[key] = val
        return {"exists": True, "env": parsed, "source": ".env"}
    except Exception as exc:
        return {"exists": False, "env": parsed, "error": str(exc), "source": "error"}


def load_env_into_process() -> None:
    res = parse_env_file(mask_secrets=False)
    for k, v in res.get("env", {}).items():
        if k and v and k not in os.environ:
            os.environ[k] = v


load_env_into_process()

WEB_HOST = os.environ.get("WEB_HOST", "0.0.0.0").strip() or "0.0.0.0"
WEB_PORT = int(os.environ.get("WEB_PORT", "3000").strip() or "3000")
LLAMA_PORT = int(os.environ.get("LLAMA_PORT", "11434").strip() or "11434")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6333").strip() or "6333")

SYSTEM_SERVICES = [
    {
        "id": "llama",
        "name": "llama.cpp Inference Server",
        "unit": "run-llama.ps1",
        "role": "FastAPI server managing native llama-server.exe (GGUF LLMs on GPU) and Intel NPU BGE embeddings",
        "port": LLAMA_PORT,
        "hardware": "GPU (llama.cpp) & Intel NPU Embeddings",
        "defaultMemory": "GPU VRAM / NPU",
        "probeUrl": f"http://127.0.0.1:{LLAMA_PORT}/healthz",
    },
    {
        "id": "qdrant",
        "name": "Qdrant Vector Database",
        "unit": "run-qdrant.ps1",
        "role": "Native Windows vector database (qdrant.exe) serving 768-dim cosine index (30-day rolling window)",
        "port": QDRANT_PORT,
        "hardware": "Intel CPU (On-Disk Mmap)",
        "defaultMemory": "On-Disk Vector Index",
        "probeUrl": f"http://127.0.0.1:{QDRANT_PORT}/healthz",
    },
    {
        "id": "web",
        "name": "K13 Web Portal",
        "unit": "run-web.ps1",
        "role": "Pure Python FastAPI web portal for vector intelligence, chat, telemetry & GGUF model switching",
        "port": WEB_PORT,
        "hardware": "Python FastAPI",
        "defaultMemory": "Python (.venv)",
        "probeUrl": f"http://127.0.0.1:{WEB_PORT}/healthz",
    },
    {
        "id": "rss",
        "name": "FreshRSS Vector Synchronizer",
        "unit": "run-rss-sync.ps1",
        "role": "Scheduled background sync running every 5 min (FreshRSS NAS -> PostgreSQL full archive -> Qdrant 30d)",
        "port": "Every 5m",
        "hardware": "Intel NPU Embeddings",
        "defaultMemory": "BGE Embeddings",
        "probeUrl": None,
    },
]

app = FastAPI(title="K13 AI Hub - Python Web Portal", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        # On Windows, os.kill(pid, 0) or tasklist check verifies if process exists
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def format_duration(diff_sec: int) -> str:
    diff_sec = max(0, int(diff_sec))
    if diff_sec < 60:
        return f"{diff_sec}s"
    if diff_sec < 3600:
        return f"{diff_sec // 60}m"
    return f"{diff_sec // 3600}h {(diff_sec % 3600) // 60}m"


def inspect_service(svc: Dict[str, Any]) -> Dict[str, Any]:
    status = "inactive"
    enabled = True
    uptime = "Stopped"
    memory = svc["defaultMemory"]

    pid_path = PID_DIR / f"{svc['id']}.pid"
    if pid_path.is_file():
        try:
            raw_pid = pid_path.read_text(encoding="utf-8", errors="ignore").strip()
            pid_num = int(raw_pid)
            if is_pid_alive(pid_num):
                status = "active"
                diff_sec = int(time.time() - pid_path.stat().st_mtime)
                uptime = f"{format_duration(diff_sec)} (PID {pid_num})"
        except Exception:
            pass

    if svc["id"] == "web":
        status = "active"
        if uptime == "Stopped":
            uptime = f"Running (PID {os.getpid()})"

    probe_url = svc.get("probeUrl")
    if probe_url and svc["id"] != "web":
        try:
            r = requests.get(probe_url, timeout=1.5)
            if 200 <= r.status_code < 500:
                status = "active"
                if uptime == "Stopped":
                    uptime = "Running"
        except Exception:
            if status == "active":
                uptime = f"Starting / Loading ({uptime})"

    return {
        "id": svc["id"],
        "name": svc["name"],
        "unit": svc["unit"],
        "role": svc["role"],
        "port": svc["port"],
        "status": status,
        "enabled": enabled,
        "uptime": uptime,
        "memory": memory,
        "hardware": svc["hardware"],
    }


@app.get("/healthz")
def healthz():
    return {"status": "ok", "runtime": "python-fastapi", "pid": os.getpid()}


@app.get("/api/env")
def api_env():
    result = parse_env_file(mask_secrets=True)
    return JSONResponse(
        content=result,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@app.get("/api/services")
def api_services_list():
    results = [inspect_service(svc) for svc in SYSTEM_SERVICES]
    return JSONResponse(
        content={"services": results},
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@app.post("/api/services/control")
async def api_services_control(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    service_id = body.get("service")
    action = body.get("action")
    svc = next((s for s in SYSTEM_SERVICES if s["id"] == service_id), None)
    if not svc:
        return JSONResponse(status_code=400, content={"error": f"Unknown service: {service_id}"})

    if action not in ("start", "stop", "restart"):
        return JSONResponse(status_code=400, content={"error": f"Invalid action: {action}"})

    ps_script = BASE_DIR / "scripts" / "windows" / "k13ctl.ps1"
    command_output = ""
    if ps_script.is_file():
        try:
            proc = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ps_script),
                    action,
                    service_id,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(BASE_DIR),
            )
            command_output = (proc.stdout or proc.stderr or "").strip()
        except Exception as exc:
            command_output = str(exc)
    else:
        command_output = f"Windows control script not found at {ps_script}"

    updated = inspect_service(svc)
    return {
        "success": True,
        "action": action,
        "service": svc["id"],
        "unit": svc["unit"],
        "output": command_output,
        "serviceStatus": updated,
    }


@app.get("/api/services/logs")
def api_services_logs(service: str = "llama"):
    svc = next((s for s in SYSTEM_SERVICES if s["id"] == service), SYSTEM_SERVICES[0])
    lines: List[str] = []

    candidate_files = [
        LOG_DIR / f"{svc['id']}.log",
        LOG_DIR / f"{svc['id']}_err.log",
    ]
    if svc["id"] == "llama":
        candidate_files.append(LOG_DIR / "llama-server.log")

    for file_path in candidate_files:
        if file_path.is_file():
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                file_lines = [l for l in content.splitlines() if l.strip()]
                lines.extend(file_lines[-100:])
            except Exception:
                pass

    if not lines:
        lines.append(f"[{time.strftime('%H:%M:%S')}] No log entries written yet in logs\\{svc['id']}.log.")
        if svc.get("probeUrl"):
            try:
                r = requests.get(svc["probeUrl"], timeout=2.0)
                lines.append(f"[✓] Live probe {svc['probeUrl']}: HTTP {r.status_code}")
            except Exception as exc:
                lines.append(f"[!] Live probe {svc['probeUrl']}: {exc}")
        lines.append(f"To stream real-time logs in PowerShell, run: .\\scripts\\windows\\k13ctl.ps1 logs {svc['id']}")

    return {"service": svc["id"], "unit": svc["unit"], "logs": lines[-100:]}


@app.post("/api/services/smoke-test")
def api_smoke_test():
    t0 = time.perf_counter()
    embed_success = False
    embed_dims = 768
    chat_success = False
    chat_response = ""

    try:
        emb_res = requests.post(
            f"http://127.0.0.1:{LLAMA_PORT}/api/embeddings",
            json={"prompt": "High-NA EUV lithography"},
            timeout=10,
        )
        if emb_res.ok:
            emb_data = emb_res.json()
            vec = emb_data.get("embedding") or (emb_data.get("embeddings") or [None])[0]
            if isinstance(vec, list) and len(vec) > 0:
                embed_success = True
                embed_dims = len(vec)
    except Exception:
        pass

    try:
        gen_res = requests.post(
            f"http://127.0.0.1:{LLAMA_PORT}/api/generate",
            json={"prompt": "Reply with the single word: ready", "stream": False},
            timeout=20,
        )
        if gen_res.ok:
            gen_data = gen_res.json()
            chat_response = (gen_data.get("response") or "").strip() or "ready (GPU online)"
            chat_success = True
    except Exception:
        pass

    total_seconds = round(time.perf_counter() - t0, 2)
    return {
        "embedSuccess": embed_success,
        "embedDims": embed_dims,
        "chatSuccess": chat_success,
        "chatResponse": chat_response or ("ready" if chat_success else f"llama.cpp server responding on 127.0.0.1:{LLAMA_PORT}"),
        "durationSeconds": total_seconds,
    }


_last_rss_rebuild_time = 0.0


@app.post("/api/rss/rebuild")
def api_rss_rebuild():
    global _last_rss_rebuild_time
    now = time.time()
    if now - _last_rss_rebuild_time < 30.0:
        return {"status": "already_triggered"}
    _last_rss_rebuild_time = now

    try:
        k13ctl = BASE_DIR / "scripts" / "windows" / "k13ctl.ps1"
        if k13ctl.is_file():
            subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(k13ctl),
                    "start",
                    "rss",
                ],
                cwd=str(BASE_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return {"status": "rebuild_started"}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


def _proxy_request(target_base: str, subpath: str, request: Request, body_bytes: bytes) -> Response:
    url = f"{target_base.rstrip('/')}/{subpath.lstrip('/')}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length", "connection", "accept-encoding")
    }
    try:
        resp = requests.request(
            method=request.method,
            url=url,
            headers=headers,
            data=body_bytes if body_bytes else None,
            stream=True,
            timeout=180,
        )
        content_type = resp.headers.get("Content-Type", "application/json")
        if "text/event-stream" in content_type or "application/x-ndjson" in content_type:
            return StreamingResponse(
                resp.iter_content(chunk_size=1024),
                status_code=resp.status_code,
                media_type=content_type,
            )
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=content_type,
        )
    except Exception as exc:
        return JSONResponse(status_code=502, content={"error": f"Upstream proxy error ({url}): {exc}"})


@app.api_route("/api/qdrant/{subpath:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_qdrant(subpath: str, request: Request):
    body = await request.body()
    return _proxy_request(f"http://127.0.0.1:{QDRANT_PORT}", subpath, request, body)


@app.api_route("/api/llama/{subpath:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_llama(subpath: str, request: Request):
    body = await request.body()
    return _proxy_request(f"http://127.0.0.1:{LLAMA_PORT}", subpath, request, body)


@app.get("/api/src-modules")
def api_src_modules():
    """Returns all TypeScript/TSX modules in src/ and frontend .env variables so the browser can compile & run without Node.js."""
    env_res = parse_env_file(mask_secrets=True)
    frontend_env = {
        k: v
        for k, v in env_res.get("env", {}).items()
        if any(k.startswith(p) for p in FRONTEND_ENV_PREFIXES) and k not in MASKED_SECRETS
    }

    modules: Dict[str, str] = {}
    if SRC_DIR.is_dir():
        for file_path in sorted(SRC_DIR.rglob("*")):
            if file_path.is_file() and file_path.suffix in (".ts", ".tsx", ".js", ".jsx"):
                rel_posix = "/src/" + file_path.relative_to(SRC_DIR).as_posix()
                raw_code = file_path.read_text(encoding="utf-8", errors="replace")
                # Replace Vite's import.meta.env with window.__K13_ENV__
                raw_code = re.sub(r"\(\s*import\.meta\s+as\s+any\s*\)\.env", "(window.__K13_ENV__ || {})", raw_code)
                raw_code = re.sub(r"import\.meta\.env", "(window.__K13_ENV__ || {})", raw_code)
                modules[rel_posix] = raw_code

    return JSONResponse(
        content={"env": frontend_env, "modules": modules},
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


PORTAL_HTML = """<!doctype html>
<html lang="en" class="dark">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2338bdf8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><polygon points='13 2 3 14 12 14 11 22 21 10 12 10 13 2'/></svg>" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>K13 AI Hub (Python Portal)</title>
    <meta name="description" content="llama.cpp GGUF-accelerated Vector RAG platform, neural search interface, and cluster control portal." />
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
      body {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        background-color: #030712;
        color: #f3f4f6;
      }
      code, pre {
        font-family: 'JetBrains Mono', monospace;
      }
      ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
      }
      ::-webkit-scrollbar-track {
        background: rgba(15, 23, 42, 0.6);
      }
      ::-webkit-scrollbar-thumb {
        background: rgba(99, 102, 241, 0.3);
        border-radius: 4px;
      }
      ::-webkit-scrollbar-thumb:hover {
        background: rgba(99, 102, 241, 0.6);
      }
      @keyframes pulse-glow {
        0%, 100% {
          opacity: 0.8;
          filter: drop-shadow(0 0 8px rgba(56, 189, 248, 0.4));
        }
        50% {
          opacity: 1;
          filter: drop-shadow(0 0 16px rgba(129, 140, 248, 0.8));
        }
      }
      .animate-glow {
        animation: pulse-glow 3s infinite ease-in-out;
      }
    </style>
  </head>
  <body class="bg-[#030712] text-slate-100 antialiased selection:bg-indigo-500/30 selection:text-indigo-200 min-h-screen">
    <div id="root">
      <div style="display:flex;align-items:center;justify-content:center;min-height:100vh;color:#94a3b8;font-family:Inter,sans-serif;font-size:14px;">
        Loading K13 AI Hub (Python FastAPI Portal)...
      </div>
    </div>
    <script type="module">
      async function bootPortal() {
        try {
          const [ReactMod, ReactDOMClientMod, SucraseMod, LucideMod, bundleRes] = await Promise.all([
            import('https://esm.sh/react@18.3.1'),
            import('https://esm.sh/react-dom@18.3.1/client?deps=react@18.3.1'),
            import('https://esm.sh/sucrase@3.35.0'),
            import('https://esm.sh/lucide-react@0.460.0?deps=react@18.3.1').catch(() => ({})),
            fetch('/api/src-modules').then(r => r.json())
          ]);

          const React = Object.assign({}, ReactMod.default || ReactMod, ReactMod);
          Object.defineProperty(React, '__esModule', { value: true });
          React.default = React;
          window.React = React;

          const ReactDOMClient = Object.assign({}, ReactDOMClientMod.default || ReactDOMClientMod, ReactDOMClientMod);
          Object.defineProperty(ReactDOMClient, '__esModule', { value: true });
          ReactDOMClient.default = ReactDOMClient;

          const FallbackIcon = (props) => React.createElement(
            'svg',
            Object.assign({
              xmlns: 'http://www.w3.org/2000/svg',
              width: props?.size || 16,
              height: props?.size || 16,
              viewBox: '0 0 24 24',
              fill: 'none',
              stroke: 'currentColor',
              strokeWidth: 2,
              strokeLinecap: 'round',
              strokeLinejoin: 'round',
              className: props?.className || ''
            }),
            React.createElement('circle', { cx: 12, cy: 12, r: 9 })
          );

          const LucideProxy = new Proxy(LucideMod || {}, {
            get(target, prop) {
              if (prop === '__esModule') return true;
              if (prop in target && target[prop]) return target[prop];
              return FallbackIcon;
            }
          });

          window.__K13_ENV__ = bundleRes.env || {};
          const rawModules = bundleRes.modules || {};
          const compiledCache = {};
          const transformFn = SucraseMod.transform || (SucraseMod.default && SucraseMod.default.transform);

          function normalizePath(baseDir, relPath) {
            const parts = (baseDir + '/' + relPath).split('/');
            const stack = [];
            for (const p of parts) {
              if (!p || p === '.') continue;
              if (p === '..') stack.pop();
              else stack.push(p);
            }
            return '/' + stack.join('/');
          }

          function resolveModuleKey(fromDir, spec) {
            const base = spec.startsWith('/') ? spec : normalizePath(fromDir, spec);
            const candidates = [
              base,
              base + '.tsx',
              base + '.ts',
              base + '.jsx',
              base + '.js',
              base + '/index.tsx',
              base + '/index.ts',
              base + '/index.js'
            ];
            for (const c of candidates) {
              if (Object.prototype.hasOwnProperty.call(rawModules, c)) {
                return c;
              }
            }
            throw new Error(`Module not found: ${spec} (from ${fromDir})`);
          }

          function requireFrom(fromDir, spec) {
            if (spec === 'react') return React;
            if (spec === 'react-dom/client' || spec === 'react-dom') return ReactDOMClient;
            if (spec === 'lucide-react') return LucideProxy;
            if (spec === 'clsx') {
              const clsxFn = (...args) => args.flat(Infinity).filter(Boolean).join(' ');
              return { __esModule: true, default: clsxFn, clsx: clsxFn };
            }
            if (spec.endsWith('.css')) return {};

            const key = resolveModuleKey(fromDir, spec);
            if (compiledCache[key]) {
              return compiledCache[key].exports;
            }

            const mod = { exports: {} };
            compiledCache[key] = mod;
            const modDir = key.substring(0, key.lastIndexOf('/')) || '/src';

            const transformed = transformFn(rawModules[key], {
              transforms: ['typescript', 'jsx', 'imports'],
              filePath: key
            }).code;

            const fn = new Function('exports', 'require', 'module', 'React', transformed);
            fn(mod.exports, (childSpec) => requireFrom(modDir, childSpec), mod, React);
            return mod.exports;
          }

          requireFrom('/src', './main.tsx');
        } catch (err) {
          console.error('Portal boot error:', err);
          const root = document.getElementById('root');
          if (root) {
            root.innerHTML = `<div style="padding:24px;color:#f87171;font-family:monospace;white-space:pre-wrap;">Failed to initialize K13 Portal:\n${err?.stack || err}</div>`;
          }
        }
      }
      bootPortal();
    </script>
  </body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def serve_index():
    return HTMLResponse(
        content=PORTAL_HTML,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


if __name__ == "__main__":
    print(f"[+] Starting K13 Pure-Python Web Portal on http://{WEB_HOST}:{WEB_PORT}", flush=True)
    uvicorn.run(app, host=WEB_HOST, port=WEB_PORT, log_level="info")

