# K13 AI Hub - Windows Native Port

Native Windows 11 / Windows Server port of the **K13 AI Stack** powered by **Intel IPEX-LLM (Intel Extension for PyTorch)** on the **Intel Arc GPU (XPU)** and **Intel NPU** with **Qdrant Vector Database** and **React Portal**.

---

## Hardware Acceleration on Windows
- **Intel Arc GPU / XPU**: Accelerated via IPEX-LLM with dynamic on-the-fly **INT4 quantization**. Intel Arc Graphics WHQL drivers natively include oneAPI Level Zero compute runtimes on Windows 11.
- **Intel NPU**: Accelerated via OpenVINO using the Intel NPU Driver for Windows (Meteor Lake / Lunar Lake / Arrow Lake).
- **CPU Fallback**: Automatic graceful fallback if requested via `SWITCH_ALLOW_CPU=on`.

---

## Prerequisites for Windows 11
1. **Intel Arc Graphics Driver**: Install latest Intel Arc WHQL graphics driver from [Intel Download Center](https://www.intel.com/content/www/us/en/download/785597/intel-arc-iris-xe-graphics-windows.html).
2. **Python 3.10, 3.11, or 3.12**: Download from [python.org](https://www.python.org/downloads/) (check "Add Python to PATH" during installation).
3. **Node.js 18+**: Download from [nodejs.org](https://nodejs.org/).
4. **Git for Windows**: Download from [git-scm.com](https://git-scm.com/).

---

## Quick Start (Two Clicks)

1. **Install everything automatically:**
   Double-click `install.bat` (or in PowerShell run `.\scripts\windows\install.ps1`).
   - Sets up Python virtual environments (`.venv` and `.venv-openvino`).
   - Installs PyTorch with Intel XPU acceleration and IPEX-LLM.
   - Downloads native Windows `qdrant.exe` into `.\bin\qdrant\`.
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

The Windows CLI provides the same management capabilities as Linux:

| Command | Description |
|---|---|
| `.\scripts\windows\k13ctl.ps1 status` | Display service status and health probes |
| `.\scripts\windows\k13ctl.ps1 start all` | Start Qdrant, OpenVINO server, and Web portal |
| `.\scripts\windows\k13ctl.ps1 stop all` | Stop all running services |
| `.\scripts\windows\k13ctl.ps1 restart openvino` | Restart IPEX-LLM inference server |
| `.\scripts\windows\k13ctl.ps1 check-hardware` | Verify Intel Arc GPU (XPU) and NPU in PyTorch |
| `.\scripts\windows\k13ctl.ps1 logs openvino` | Stream live logs for model switching & generation |
| `.\scripts\windows\k13ctl.ps1 fix-transformers` | Ensure `transformers<=4.44.2` compatibility |
| `.\scripts\windows\k13ctl.ps1 test` | Run embedding and chat inference smoke tests |

---

## Model Selection on Windows
All curated models in the portal are supported with 4-bit INT4 quantization on the Intel Arc GPU:
- **DeepSeek R1 Distill Qwen 7B** (Reasoning with `<think>` stream)
- **DeepSeek R1 Distill 1.5B** (Ultra-fast lightweight reasoning)
- **Qwen2.5 Coder 7B Instruct** (IDE coding & bash assistant)
- **Qwen2.5 7B Instruct** (General news briefs & Qdrant RAG)
- **BAAI/bge-base-en-v1.5** (768-dim embeddings pinned to Intel NPU)

---

## Endpoints
- **Web Portal**: `http://localhost:3000`
- **Inference Server (OpenAI & Ollama compatible)**: `http://localhost:11434`
  - `/v1/chat/completions` (OpenAI format for Continue / Cursor / VS Code)
  - `/api/chat` and `/api/generate` (Ollama format)
  - `/api/embeddings` and `/v1/embeddings`
  - `/api/switch-model` (Dynamic INT4 switching)
- **Qdrant Vector Database**: `http://localhost:6333/dashboard`
