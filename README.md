# K13 AI Hub - Windows Native Edition (llama.cpp GGUF & Qdrant RAG Platform)

A full-featured Windows 11 / Windows Server application powered by native **`llama.cpp` (`llama-server.exe`)** for Hugging Face GGUF LLM inference, **Hugging Face Transformers** for BGE vector embeddings, native Windows **Qdrant Vector Database**, and a **React & Vite Portal**.

```
 browser ──► K13 React Portal (:3000) ──┬──► llama.cpp Server (:11434)   [GGUF LLM on GPU + BGE Embeddings]
                                        └──► Qdrant Vector DB (:6333)    [768-dim Cosine Index (qdrant.exe)]
```

---

## Why `llama.cpp` on Windows?
- **Full Hugging Face GGUF Ecosystem**: Run any modern architecture on Hugging Face—including **Qwen3**, **Gemma 3**, **DeepSeek R1**, **Phi-4**, **Llama 3.2 / 3.3**, **Mistral**, and **Qwen2.5-Coder**—in `Q4_K_M`, `Q5_K_M`, `Q6_K`, or `Q8_0` quantizations.
- **Native GPU Acceleration**: Offloads model layers (`-ngl 99`) directly to your GPU via `llama-server.exe` (Vulkan / SYCL / CUDA) without version-locked Python compiler chains.
- **Automatic GGUF Resolution**: Enter any Hugging Face GGUF repository (or standard model ID) in the Model Switcher and the server automatically downloads the optimal `.gguf` quantization into `data\models\` and hot-swaps `llama-server.exe`.

---

## Prerequisites for Windows
1. **`llama.cpp` installed on Windows**: Ensure `llama-server.exe` is in your system `PATH`, or set `LLAMA_SERVER_BIN` / `LLAMA_CPP_DIR` in `.env`.
2. **Python 3.10+**: Download from [python.org](https://www.python.org/downloads/) (check "Add Python to PATH" during installation).
3. **Node.js 18+**: Download from [nodejs.org](https://nodejs.org/).
4. **Git for Windows**: Download from [git-scm.com](https://git-scm.com/).

---

## Quick Start

1. **Install dependencies:**
   Double-click `install.bat` (or in PowerShell run `.\scripts\windows\install.ps1`).
   - Sets up Python virtual environment (`.venv`).
   - Installs FastAPI, Hugging Face Hub, and embedding dependencies.
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
| `.\scripts\windows\k13ctl.ps1 start all` | Start Qdrant, llama.cpp server, Web portal, and RSS sync |
| `.\scripts\windows\k13ctl.ps1 stop all` | Stop all running services |
| `.\scripts\windows\k13ctl.ps1 restart llama` | Restart `llama.cpp` inference server |
| `.\scripts\windows\k13ctl.ps1 check-hardware` | Verify `llama-server.exe` binary and Python stack |
| `.\scripts\windows\k13ctl.ps1 logs llama` | Stream live logs for model switching & generation |
| `.\scripts\windows\k13ctl.ps1 install-qdrant-ui` | Download & install Qdrant Web GUI Dashboard |
| `.\scripts\windows\k13ctl.ps1 test` | Run embedding and chat inference smoke tests |

---

## Endpoints
- **Web Portal**: `http://localhost:3000`
- **Inference Server (OpenAI & Ollama compatible)**: `http://localhost:11434`
  - `/v1/chat/completions` (OpenAI format for Continue / Cursor / VS Code)
  - `/api/chat` and `/api/generate` (Ollama format)
  - `/api/embeddings` and `/v1/embeddings`
  - `/api/switch-model` (Dynamic GGUF downloading & hot-swapping)
- **Qdrant Vector Database**: `http://localhost:6333/dashboard`
