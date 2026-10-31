# K13 AI Hub - Windows Native Edition (Intel IPEX-LLM & OpenVINO RAG Platform)

A full-featured Windows 11 / Windows Server application powered by **Intel IPEX-LLM (Intel Extension for PyTorch)** on the **Intel Arc GPU (XPU)** and **OpenVINO** on the **Intel NPU**, paired with native Windows **Qdrant Vector Database** and a **React & Vite Portal**.

```
 browser ──► K13 React Portal (:3000) ──┬──► IPEX-LLM / OpenVINO Server (:11434)  [LLM on Intel Arc GPU + BGE on Intel NPU]
                                        └──► Qdrant Vector DB (:6333)             [768-dim Cosine Index (qdrant.exe)]
```

---

## Hardware Acceleration on Windows
- **Intel Arc GPU / XPU**: Accelerated via IPEX-LLM with dynamic on-the-fly **4-bit INT4 quantization** (~6.8 GB VRAM cap enforcement and CPU rollback handling). Intel Arc Graphics WHQL drivers natively include oneAPI Level Zero compute runtimes on Windows 11.
- **Intel NPU**: Accelerated via OpenVINO using the Intel NPU Driver for Windows (Lunar Lake / Meteor Lake / Arrow Lake) for `BAAI/bge-base-en-v1.5` (768 dims) and `BAAI/bge-small-en-v1.5` (384 dims) embeddings.
- **CPU Fallback**: Automatic graceful fallback if requested via `SWITCH_ALLOW_CPU=on`.

---

## Features

1. **Neural Vector RAG & Intelligence Chat**:
   - Hybrid vector + exact URL lookup retrieval.
   - Grounded citations with direct article hyperlinks.
   - Persona prompts: Objective News Analyst, Executive Intelligence Brief, Technical Deep Dive, and Analytical Unbiased (6-principle framework).
   - Timeframe filter (All Time, 24 Hours, 7 Days, 30 Days, Custom range with timezone selection and date-time pickers).
   - Feed and Group facet filtering.
   - Real-time token streaming with `<think>...</think>` reasoning stripping.
   - Comprehensive Query Statistics: Tokens/s, Output tokens, Prompt tokens, Time to 1st token (TTFT), Timing breakdown, and Retrieval & Truncation report.
   - Self-contained standalone HTML report export (`answerToHtml`).

2. **Intel Hardware & Model Engine Switcher**:
   - Intel Arc GPU (XPU): INT4 chat & reasoning models with ~6.8 GB VRAM cap enforcement and CPU rollback handling.
   - Intel NPU: BGE Base (768 dims) and BGE Small (384 dims) models.
   - Force reload on GPU action for CPU fallbacks.
   - Custom Hugging Face repository loader.

3. **Daily Briefing Generator**:
   - Generates 4 numbered summaries `[1]`–`[4]`, synopsis, and verified real source citations from 24-hour news feeds.
   - Formats: Markdown (with `[[n]](url)` hyperlinks) and Facebook post text.
   - Export to `.md` or `.txt` and clipboard copy.

4. **Windows Services & Cluster Control (`k13ctl.ps1`)**:
   - Service health monitoring: `openvino`, `qdrant`, `web`, `rss`.
   - Actions: Start, Stop, Restart, Status.
   - Smoke test execution (`k13ctl.ps1 test`) checking embedding dimensions and chat response.
   - Live service log viewer (`logs\<service>.log`).

5. **Configuration Inspector (`.env`)**:
   - Environment parameters viewer, platform architecture guidelines, and cluster mode switcher (Simulated Intel Cluster vs Live Local Endpoints).

---

## Prerequisites for Windows
1. **Intel Arc Graphics Driver & Intel NPU Driver**: Install the latest WHQL drivers from [Intel Download Center](https://www.intel.com/content/www/us/en/download/785597/intel-arc-iris-xe-graphics-windows.html).
2. **Python 3.10, 3.11, or 3.12**: Download from [python.org](https://www.python.org/downloads/) (check "Add Python to PATH" during installation).
3. **Node.js 18+**: Download from [nodejs.org](https://nodejs.org/).
4. **Git for Windows**: Download from [git-scm.com](https://git-scm.com/).

---

## Quick Start

1. **Install everything automatically:**
   Double-click `install.bat` (or in PowerShell run `.\scripts\windows\install.ps1`).
   - Sets up Python virtual environments (`.venv` and `.venv-openvino`).
   - Installs PyTorch with Intel XPU acceleration and IPEX-LLM.
   - Downloads native Windows `qdrant.exe` and Web UI into `.\bin\qdrant\`.
   - Builds the React Web Portal.
   - Copies `.env.example` to `.env`.

2. **Start all services:**
   Double-click `start-all.bat` (or in PowerShell run `.\scripts\windows\k13ctl.ps1 start all`).
   - Automatically opens your browser to: **http://localhost:3000**

3. **Check status anytime:**
   Double-click `status.bat` or run:
   ```powershell
   .\scripts\windows\k13ctl.ps1 status
   ```

4. **Stop services:**
   Double-click `stop-all.bat` or run:
   ```powershell
   .\scripts\windows\k13ctl.ps1 stop all
   ```

---

## PowerShell CLI (`k13ctl.ps1`)

| Command | Description |
|---|---|
| `.\scripts\windows\k13ctl.ps1 status` | Display service status and health probes |
| `.\scripts\windows\k13ctl.ps1 start all` | Start Qdrant, OpenVINO server, Web portal, and RSS sync |
| `.\scripts\windows\k13ctl.ps1 stop all` | Stop all running services |
| `.\scripts\windows\k13ctl.ps1 restart openvino` | Restart IPEX-LLM inference server |
| `.\scripts\windows\k13ctl.ps1 check-hardware` | Verify Intel Arc GPU (XPU) and NPU in PyTorch & OpenVINO |
| `.\scripts\windows\k13ctl.ps1 logs openvino` | Stream live logs for model switching & generation |
| `.\scripts\windows\k13ctl.ps1 fix-transformers` | Ensure `transformers<=4.44.2` compatibility |
| `.\scripts\windows\k13ctl.ps1 install-qdrant-ui` | Download & install Qdrant Web GUI Dashboard |
| `.\scripts\windows\k13ctl.ps1 test` | Run embedding and chat inference smoke tests |

---

## Endpoints
- **Web Portal**: `http://localhost:3000`
- **Inference Server (OpenAI & Ollama compatible)**: `http://localhost:11434`
  - `/v1/chat/completions` (OpenAI format for Continue / Cursor / VS Code)
  - `/api/chat` and `/api/generate` (Ollama format)
  - `/api/embeddings` and `/v1/embeddings`
  - `/api/switch-model` (Dynamic INT4 switching)
- **Qdrant Vector Database**: `http://localhost:6333/dashboard`
