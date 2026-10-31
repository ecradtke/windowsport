#!/usr/bin/env python3
"""
K13 AI Hub - Windows Hardware & llama.cpp Stack Verification
Verifies native llama-server.exe binary, GPU backend, and Hugging Face Embeddings.
"""
import os
import sys
import subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)

print("=" * 60)
print("  K13 AI Hub - Windows llama.cpp & Stack Verification")
print("=" * 60)

# 1. Locate llama-server.exe
try:
    from llama.server import find_llama_server_binary
    bin_path = find_llama_server_binary()
    if bin_path:
        print(f"[OK] llama-server.exe located: {bin_path}")
        try:
            res = subprocess.run([bin_path, "--version"], capture_output=True, text=True, timeout=10)
            ver_out = (res.stdout or res.stderr or "").strip().splitlines()
            if ver_out:
                print(f"     Version info: {ver_out[0]}")
        except Exception as e_ver:
            print(f"     (Could not query --version: {e_ver})")
    else:
        print("[-] llama-server.exe not found in PATH or default locations.")
        print("    Tip: Set LLAMA_SERVER_BIN or LLAMA_CPP_DIR in .env pointing to your llama.cpp install.")
except Exception as e:
    print(f"[-] Error checking llama-server binary: {e}")

# 2. Check Hugging Face Hub & Transformers (for GGUF download + BGE Embeddings)
try:
    import huggingface_hub
    import transformers
    import torch
    print(f"[OK] huggingface_hub: {huggingface_hub.__version__}")
    print(f"[OK] transformers:    {transformers.__version__}")
    print(f"[OK] torch:           {torch.__version__}")
except Exception as e:
    print(f"[-] Python dependency warning: {e}")

print("=" * 60)
