# System Architecture & Platform Guidelines: K13 AI Hub on Ubuntu Server (native IPEX-LLM)

## Platform directive
This deployment runs **natively on Ubuntu Server** (minimal desktop) with **systemd**. There are **no containers**:
never suggest Docker, Compose or `host.docker.internal`. It is **pure Intel IPEX-LLM (Intel Extension for PyTorch), NOT Ollama and NOT llama.cpp**.
Use bash, systemd and Linux paths.

## Services (systemd units run as the installing user)
| Unit | Role | Default address |
|---|---|---|
| `k13-openvino.service` | `openvino/server.py` (FastAPI): chat LLM via `ipex-llm` (Intel Extension for PyTorch) on the Intel Arc GPU (XPU), embeddings (`bge`) on the Intel NPU with CPU fallback. Ollama endpoints (`/api/chat`, `/api/generate`, `/api/embeddings`, `/api/embed`, `/api/tags`, switch endpoints) and OpenAI endpoints (`/v1/chat/completions`, `/v1/embeddings`) | `127.0.0.1:11434` |
| `k13-qdrant.service` | native Qdrant in `/opt/k13/qdrant`, data in `K13_DATA_DIR/qdrant` | `:6333` |
| `k13-web.service` | React portal `server.ts` / Vite | `:3000` |
| `k13-rss-sync.timer` | runs `rss/sync_freshrss.py` every 5 minutes (FreshRSS -> Postgres -> Qdrant) | - |

External: FreshRSS API and PostgreSQL (`fetch42`, `freshrss`) on the NAS; backups go to `DROPIT_DIR`.

## Hardware topology
- **Intel Arc GPU / XPU** (`/dev/dri`): chat & reasoning LLMs via IPEX-LLM, default `Qwen/Qwen2.5-7B-Instruct`. On this machine the GPU runtime allocation caps at ~6.8 GB. IPEX-LLM dynamically quantizes standard Hugging Face repositories to 4-bit INT4 directly in memory.
- **Intel NPU** (`/dev/accel/accel0`): embeddings, `BAAI/bge-base-en-v1.5` (768 dims, the default at every start and install), static shape `(1, 512)`.
- **Intel CPU**: fallback. A model switch that only fits on the CPU is rolled back unless `SWITCH_ALLOW_CPU=on`.

## Layout
`openvino/` IPEX-LLM server - `src/` React portal - `rss/` sync - `systemd/` unit templates (`@USER@`, `@REPO@`) -
`scripts/` installer, control, backup scripts - `docs/` guides. Config is a single `.env` parsed (never sourced) by `scripts/_lib.sh`;
the `scripts/run-*.sh` wrappers that systemd launches read it, so a service restart picks up edits.

## Rules for agents
1. **IPEX-LLM (Intel Extension for PyTorch) does inference.** Do not reintroduce llama.cpp, Ollama or containers.
2. **Embedding dimension must match the Qdrant collection** (768 for the default `bge-base-en-v1.5`, 384 for `bge-small-en-v1.5`).
3. **Never put secrets in git.** Credentials live only in `.env`. In `.env`: comments on their own line, no inline `# ...`; quote values with spaces.
4. systemd units are templates in `systemd/`; `scripts/install.sh --units-only` renders them. Services start via `scripts/run-*.sh`.
5. Qdrant URL/hosts: the portal reads `QDRANT_URL`, the sync reads `QDRANT_HOST`/`QDRANT_PORT` (derived in `run-rss-sync.sh`); the portal and sync reach the server at `127.0.0.1:OV_PORT`.
