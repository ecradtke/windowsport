# Platform Rule: K13 AI Hub on Windows (native IPEX-LLM & OpenVINO, no containers)

- Hardware: Intel Core Ultra (Lunar Lake class) with Intel Arc GPU (XPU) + Intel NPU. OS: Windows 11 / Windows Server. Services run as native Windows processes managed by PowerShell (`scripts\windows\k13ctl.ps1`).
- All inference is **IPEX-LLM & OpenVINO** (`openvino\server.py`, port 11434): LLM on the Intel Arc GPU (XPU) with dynamic INT4 quantization, embeddings (`BAAI/bge-base-en-v1.5`, 768 dims, default) on the Intel NPU, CPU fallback. Vector DB: native Windows **Qdrant** (`bin\qdrant\qdrant.exe`) on 6333.
- No Docker, no containers, no WSL, no systemd, no Ollama, no llama.cpp. Use `scripts\windows\k13ctl.ps1` and `scripts\windows\install.ps1` (or root `.bat` launchers).
- The GPU runtime caps at ~6.8 GB here: 7B–8B INT4 models are the largest LLMs that fit on the GPU without `SWITCH_ALLOW_CPU=on`.

