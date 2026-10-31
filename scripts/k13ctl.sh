#!/usr/bin/env bash
# Control the K13 services.
#   k13ctl.sh status
#   k13ctl.sh {start|stop|restart} {qdrant|openvino|web|rss|all}
#   k13ctl.sh logs {qdrant|openvino|web|rss}
#   k13ctl.sh test            embedding + chat smoke tests
#   k13ctl.sh check-hardware  verify Intel Arc GPU (XPU) & PyTorch device status
#   k13ctl.sh fix-gpu         install Level Zero drivers & fix sudoers
#   k13ctl.sh install-ipex    install IPEX-LLM PyTorch XPU environment
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
load_k13_env

unit_of() {
  case "$1" in
    qdrant) echo k13-qdrant.service ;; openvino) echo k13-openvino.service ;;
    web) echo k13-web.service ;; rss) echo k13-rss-sync.timer ;;
    *) die "unknown service '$1' (qdrant|openvino|web|rss|all)" ;;
  esac
}
ALL=(qdrant openvino web rss)

case "${1:-status}" in
  status)
    for s in "${ALL[@]}"; do
      u="$(unit_of "$s")"; printf '%-8s %-10s' "$s" "$(systemctl is-active "$u" 2>/dev/null)"
      printf ' (%s)\n' "$(systemctl is-enabled "$u" 2>/dev/null)"
    done
    echo
    echo "--- health ---"
    printf 'qdrant : '; curl -fs --max-time 3 "http://127.0.0.1:${QDRANT_PORT}/healthz" || echo "not responding"; echo
    printf 'openvino: '; curl -fs --max-time 20 "http://127.0.0.1:${OV_PORT}/healthz" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["status"], "| LLM:", d.get("llm_hardware"), d.get("current_model"), "| embeddings:", d.get("embed_hardware"))' 2>/dev/null || echo "not responding (still loading models?)"
    ;;
  start|stop|restart)
    act="$1"; target="${2:-}"; [[ -n "$target" ]] || die "usage: $0 $act {qdrant|openvino|web|rss|all}"
    if [[ "$target" == all ]]; then for s in "${ALL[@]}"; do sudo systemctl "$act" "$(unit_of "$s")"; done
    else sudo systemctl "$act" "$(unit_of "$target")"; fi
    ;;
  logs)
    [[ -n "${2:-}" ]] || die "usage: $0 logs {qdrant|openvino|web|rss}"
    u="$(unit_of "$2")"; [[ "$2" == rss ]] && u=k13-rss-sync.service
    journalctl -fu "$u" -n 100
    ;;
  test)
    log "Embedding test..."
    curl -fs "http://127.0.0.1:${OV_PORT}/api/embeddings" -d '{"prompt":"High-NA EUV lithography"}' \
      | python3 -c 'import sys,json; v=json.load(sys.stdin)["embedding"]; print("  vector dimensions:", len(v))' || warn "embedding test failed"
    log "Chat test..."
    curl -fs "http://127.0.0.1:${OV_PORT}/api/generate" -d '{"prompt":"Reply with the single word: ready","stream":false}' \
      | python3 -c 'import sys,json; print("  ", json.load(sys.stdin)["response"].strip()[:200])' || warn "chat test failed"
    log "OpenAI coding endpoint test (/v1/chat/completions)..."
    curl -fs "http://127.0.0.1:${OV_PORT}/v1/chat/completions" -H "Content-Type: application/json" \
      -d '{"messages":[{"role":"user","content":"Reply with: ready"}],"stream":false}' \
      | python3 -c 'import sys,json; print("  ", json.load(sys.stdin)["choices"][0]["message"]["content"].strip()[:200])' || warn "OpenAI endpoint test failed"
    ;;
  install-ipex)
    PY="$(env_get OPENVINO_PYTHON)"
    PY="${PY:-$BASE_DIR/.venv-openvino/bin/python}"
    [[ -x "$PY" ]] || die "Python environment not found at $PY (run ./scripts/install.sh first)"
    log "Preparing Python environment ($PY)..."
    "$PY" -m pip install -q --upgrade pip

    # 1. Clean out conflicting non-Intel/CUDA PyTorch wheels if present
    log "Checking for conflicting CUDA/non-XPU PyTorch packages..."
    "$PY" -c '
import sys
try:
    import torch
    if "+cu" in torch.__version__ or "+rocm" in torch.__version__:
        sys.exit(0)
    sys.exit(1)
except Exception:
    sys.exit(1)
' 2>/dev/null && {
      log "Detected CUDA/incompatible PyTorch wheel. Removing to allow clean Intel XPU installation..."
      "$PY" -m pip uninstall -y torch torchvision torchaudio intel-extension-for-pytorch ipex-llm 2>/dev/null || true
    }

    # 2. Ensure PyTorch XPU is present
    "$PY" -c 'import torch; assert "+xpu" in torch.__version__' 2>/dev/null || {
      log "Installing PyTorch with Intel Arc XPU support from PyTorch repository..."
      "$PY" -m pip install --pre --upgrade torch torchvision torchaudio --index-url https://download.pytorch.org/whl/xpu
    }

    # 3. Install IPEX-LLM (using --no-deps so pip does not force legacy torch==2.1.0a0)
    log "Installing IPEX-LLM for Intel Arc GPU (XPU)..."
    "$PY" -m pip install --pre --upgrade ipex-llm --no-deps \
      || "$PY" -m pip install --pre --upgrade "ipex-llm[xpu_2.6]" --extra-index-url https://download.pytorch.org/whl/xpu \
      || "$PY" -m pip install --pre --upgrade "ipex-llm[xpu]" --extra-index-url https://pytorch-extension.intel.com/release-whl/stable/xpu/us/

    log "Installing supporting packages (transformers, accelerate, sentencepiece)..."
    "$PY" -m pip install -q transformers accelerate sentencepiece protobuf torchvision || true
    log "Installing server dependencies from requirements.txt..."
    "$PY" -m pip install -r "$BASE_DIR/openvino/requirements.txt"

    ok "IPEX-LLM installation complete. Checking XPU device..."
    "$PY" -c '
import os, sys
os.environ.setdefault("ZE_INIT_ALL_DRIVER_TYPES_ENABLE", "1")
os.environ.setdefault("ONEAPI_DEVICE_SELECTOR", "level_zero:*")
try:
    import intel_extension_for_pytorch as ipex
except Exception:
    pass
import torch
xpu = hasattr(torch, "xpu") and torch.xpu.is_available()
count = torch.xpu.device_count() if xpu else 0
print("PyTorch version:", torch.__version__)
print("Intel Arc GPU (XPU) available:", "[✓] YES" if xpu else "[-] NO")
print("Intel Arc GPU (XPU) device count:", count)
if count > 0:
    print("GPU device name:", torch.xpu.get_device_name(0))
else:
    print("[-] Device count is 0. Ensure Level Zero runtime is installed on Ubuntu:")
    print("    sudo apt install -y libze1 libze-intel-gpu1 intel-opencl-icd clinfo")
    print("    sudo usermod -aG render,video $USER")
try:
    import ipex_llm
    from ipex_llm.transformers import AutoModelForCausalLM
    print("IPEX-LLM:", "[✓] READY (version " + str(ipex_llm.__version__) + ")")
except Exception as e:
    print("[-] IPEX-LLM import warning:", e)
'
    sudo systemctl restart k13-openvino.service
    ok "k13-openvino service restarted."
    ;;
  check-hardware)
    PY="$(env_get OPENVINO_PYTHON)"
    PY="${PY:-$BASE_DIR/.venv-openvino/bin/python}"
    log "Checking Intel Hardware and IPEX-LLM environment ($PY)..."
    "$PY" -c '
import os
os.environ.setdefault("ZE_INIT_ALL_DRIVER_TYPES_ENABLE", "1")
os.environ.setdefault("ONEAPI_DEVICE_SELECTOR", "level_zero:*")
import torch
print("[*] PyTorch:", torch.__version__)
try:
    import intel_extension_for_pytorch as ipex
    print("[+] Intel Extension for PyTorch backend: available")
except Exception as e:
    print("[-] Intel Extension for PyTorch backend:", e)
try:
    import ipex_llm
    print("[+] IPEX-LLM package: version", ipex_llm.__version__)
except Exception as e:
    print("[-] IPEX-LLM package: NOT FOUND (" + str(e) + ")")
xpu = hasattr(torch, "xpu") and torch.xpu.is_available()
count = torch.xpu.device_count() if xpu else 0
print("[*] Intel Arc GPU / XPU available in PyTorch:", "[✓] YES" if xpu else "[✗] NO")
print("[*] Intel Arc GPU device count:", count)
if count > 0:
    print("    Device:", torch.xpu.get_device_name(0))
else:
    print("[-] Device count is 0. To enable GPU hardware discovery on Ubuntu, run:")
    print("    sudo apt install -y libze1 libze-intel-gpu1 intel-opencl-icd clinfo")
    print("    sudo usermod -aG render,video $USER")
'
    ;;
  fix-gpu)
    log "Fixing sudoers configuration..."
    sudo rm -f /etc/sudoers.d/k13-services
    sudo tee /etc/sudoers.d/k13-services >/dev/null <<SUDOERS
${USER} ALL=(ALL) NOPASSWD: /bin/systemctl, /usr/bin/systemctl, /bin/journalctl, /usr/bin/journalctl
SUDOERS
    sudo chmod 0440 /etc/sudoers.d/k13-services
    log "Installing Intel Level Zero and OpenCL compute drivers for Ubuntu..."
    sudo apt update
    sudo apt install -y libze1 libze-intel-gpu1 intel-opencl-icd clinfo
    log "Ensuring user '$USER' is member of 'render' and 'video' groups..."
    sudo usermod -aG render,video "$USER"
    ok "Driver setup complete. Checking hardware detection..."
    echo
    "$BASE_DIR/scripts/k13ctl.sh" check-hardware
    ;;
  *) sed -n 2,8p "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
