# System Architecture & Platform Guidelines: K13 AI Hub on Windows (native IPEX-LLM)

## Platform directive
This application runs **natively on Windows (Windows 11 / Windows Server)** managed via **PowerShell** (`scripts\windows\*.ps1`) and Windows batch launchers (`*.bat`). There are **no containers**:
never suggest Docker, Compose, WSL, systemd, or `host.docker.internal`. It is **pure Intel IPEX-LLM (Intel Extension for PyTorch) and OpenVINO, NOT Ollama and NOT llama.cpp**.
Use PowerShell, `.bat` launchers, and Windows paths.

## Services (managed as native Windows processes via `scripts\windows\k13ctl.ps1`)
| Service ID | Runner Script | Role | Default address |
|---|---|---|---|
| `openvino` | `scripts\windows\run-openvino.ps1` | `openvino\server.py` (FastAPI): chat LLM via `ipex-llm` (Intel Extension for PyTorch) on the Intel Arc GPU (XPU), embeddings (`bge`) on the Intel NPU with CPU fallback. Ollama endpoints (`/api/chat`, `/api/generate`, `/api/embeddings`, `/api/embed`, `/api/tags`, switch endpoints) and OpenAI endpoints (`/v1/chat/completions`, `/v1/embeddings`) | `127.0.0.1:11434` |
| `qdrant` | `scripts\windows\run-qdrant.ps1` | native Windows Qdrant in `bin\qdrant\qdrant.exe`, data in `data\qdrant` (or `K13_DATA_DIR\qdrant`) | `:6333` |
| `web` | `scripts\windows\run-web.ps1` | React portal (Vite server & middleware) | `:3000` |
| `rss` | `scripts\windows\run-rss-sync.ps1` | runs `rss\sync_freshrss.py` on a 5-minute interval (FreshRSS -> Postgres -> Qdrant) | - |

External: FreshRSS API and PostgreSQL (`fetch42`, `freshrss`) on the NAS; backups go to `DROPIT_DIR`.

## Hardware topology
- **Intel Arc GPU / XPU** (Intel Arc Graphics WHQL driver / oneAPI Level Zero): chat & reasoning LLMs via IPEX-LLM, default `Qwen/Qwen2.5-7B-Instruct`. On this machine (Intel Core Ultra / Lunar Lake class) the GPU runtime allocation caps at ~6.8 GB. IPEX-LLM dynamically quantizes standard Hugging Face repositories to 4-bit INT4 directly in memory.
- **Intel NPU** (Intel NPU Driver for Windows / OpenVINO): embeddings, `BAAI/bge-base-en-v1.5` (768 dims, the default at every start and install), static shape `(1, 512)`.
- **Intel CPU**: fallback. A model switch that only fits on the CPU is rolled back unless `SWITCH_ALLOW_CPU=on`.

## Layout
`openvino\` IPEX-LLM server - `src\` React portal - `rss\` sync - `scripts\windows\` PowerShell installer, control CLI (`k13ctl.ps1`), hardware verifier (`verify_hardware.py`), and service runners (`run-*.ps1`) - root `*.bat` quick-launchers (`install.bat`, `start-all.bat`, `stop-all.bat`, `status.bat`, `check-hardware.bat`).
Config is a single `.env` file parsed (never sourced) by the PowerShell runner scripts, Python services, and Vite middleware; restarting a service via `.\scripts\windows\k13ctl.ps1 restart <service>` picks up `.env` edits.

## Rules for agents
1. **IPEX-LLM (Intel Extension for PyTorch) and OpenVINO do inference.** Do not reintroduce llama.cpp, Ollama, WSL, systemd, or containers.
2. **Embedding dimension must match the Qdrant collection** (768 for the default `bge-base-en-v1.5`, 384 for `bge-small-en-v1.5`).
3. **Never put secrets in git.** Credentials live only in `.env`. In `.env`: comments on their own line, no inline `# ...`; quote values with spaces.
4. Services are managed natively on Windows via `.\scripts\windows\k13ctl.ps1` (with PID tracking in `data\pids\` and logs in `logs\`) and start via `scripts\windows\run-*.ps1`.
5. Qdrant URL/hosts: the portal reads `QDRANT_URL`, the sync reads `QDRANT_HOST`/`QDRANT_PORT`; the portal and sync reach the inference server at `127.0.0.1:OV_PORT`.
