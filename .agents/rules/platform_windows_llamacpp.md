# Platform Rule: K13 AI Hub on Windows (native llama.cpp, no containers)

- OS: Windows 11 / Windows Server. Services run as native Windows processes managed by PowerShell (`scripts\windows\k13ctl.ps1`).
- All LLM inference is **llama.cpp** (`llama\server.py` managing `llama-server.exe`, port 11434) with Hugging Face GGUF models offloaded to the GPU (`-ngl 99`), and `BAAI/bge-base-en-v1.5` (768 dims, default) embeddings. Vector DB: native Windows **Qdrant** (`bin\qdrant\qdrant.exe`) on 6333.
- No OpenVINO, no IPEX-LLM, no Docker, no containers, no WSL, no systemd. Use `scripts\windows\k13ctl.ps1` and `scripts\windows\install.ps1` (or root `.bat` launchers).

