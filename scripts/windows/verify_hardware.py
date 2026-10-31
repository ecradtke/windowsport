#!/usr/bin/env python3
"""
K13 AI Hub - Windows Hardware & Inference Stack Verification
Verifies Intel Arc GPU (XPU) via PyTorch / IPEX-LLM and Intel NPU via OpenVINO.
"""
import os
import sys

# Ensure Level Zero drivers and oneAPI selectors are initialized
os.environ.setdefault("ZE_INIT_ALL_DRIVER_TYPES_ENABLE", "1")
os.environ.setdefault("ONEAPI_DEVICE_SELECTOR", "level_zero:*")

print("=" * 60)
print("  K13 AI Hub - Hardware & Inference Stack Verification")
print("=" * 60)

# 1. PyTorch & Intel Arc GPU (XPU)
try:
    import torch
    print(f"[*] PyTorch Version: {torch.__version__}")
    xpu_ready = hasattr(torch, "xpu") and torch.xpu.is_available()
    dev_count = torch.xpu.device_count() if xpu_ready else 0
    if xpu_ready and dev_count > 0:
        dev_name = torch.xpu.get_device_name(0)
        print(f"[OK] Intel Arc GPU (XPU): READY ({dev_count} device(s) found)")
        print(f"     Device 0: {dev_name}")
    else:
        print("[-] Intel Arc GPU (XPU): NOT DETECTED or 0 devices found.")
        print("    Tip: Ensure Intel Arc Graphics Windows WHQL driver is installed.")
except Exception as e:
    print(f"[-] PyTorch error: {e}")

# 2. IPEX-LLM Verification
try:
    import ipex_llm
    from ipex_llm.transformers import AutoModelForCausalLM
    print(f"[OK] IPEX-LLM: READY (version {ipex_llm.__version__})")
except Exception as e:
    print(f"[-] IPEX-LLM Warning: {e}")
    if "OffloadedCache" in str(e):
        print("    Tip: Run .\\scripts\\windows\\k13ctl.ps1 fix-transformers to pin transformers<=4.44.2")

# 3. OpenVINO & Intel NPU Verification
try:
    import openvino as ov
    core = ov.Core()
    devices = core.available_devices
    print(f"[*] OpenVINO Available Devices: {', '.join(devices)}")
    if "NPU" in devices:
        print("[OK] Intel NPU: READY (Fast embeddings accelerated on NPU)")
    elif "GPU" in devices:
        print("[*] Intel NPU not present; OpenVINO GPU/CPU acceleration available.")
    else:
        print("[*] OpenVINO CPU mode active.")
except Exception as e:
    print(f"[-] OpenVINO Warning: {e}")

print("=" * 60)
