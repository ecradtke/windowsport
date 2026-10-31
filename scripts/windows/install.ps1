# ==============================================================================
# K13 AI Hub - Complete Windows 11 / Windows Server Native Installer
# Sets up Intel Arc GPU (XPU), Intel NPU, Qdrant, IPEX-LLM & Web Portal
# ==============================================================================
param(
    [switch]$SkipQdrant = $false,
    [switch]$SkipNpm = $false
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BaseDir = Resolve-Path "$ScriptDir\..\.."
Set-Location $BaseDir

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  K13 AI Hub - Native Windows Setup (Intel Arc / NPU)     " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Target Directory: $BaseDir"

# 1. Environment file check
$EnvFile = Join-Path $BaseDir ".env"
$EnvExample = Join-Path $BaseDir ".env.example"
if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample $EnvFile
        Write-Host "[+] Created .env from .env.example. Please review settings." -ForegroundColor Green
    }
}

# 2. Check Prerequisites
Write-Host "`n[*] Checking system prerequisites..." -ForegroundColor Yellow
$PythonCmd = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    Write-Host "[-] Python is not installed or not in PATH! Please install Python 3.10, 3.11, or 3.12 from python.org." -ForegroundColor Red
    exit 1
}
$NodeCmd = Get-Command node.exe -ErrorAction SilentlyContinue
if (-not $NodeCmd) {
    Write-Host "[-] Node.js is not installed or not in PATH! Please install Node.js 18+ from nodejs.org." -ForegroundColor Red
    exit 1
}
Write-Host "[✓] Python: $(python --version)" -ForegroundColor Green
Write-Host "[✓] Node.js: $(node --version)" -ForegroundColor Green

# 3. Create Directories
$Dirs = @(
    "bin\qdrant",
    "data\models",
    "data\qdrant\storage",
    "data\qdrant\snapshots",
    "logs"
)
foreach ($d in $Dirs) {
    $fullPath = Join-Path $BaseDir $d
    if (-not (Test-Path $fullPath)) {
        New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
    }
}

# 4. Create and configure Python virtual environments
Write-Host "`n[*] Configuring RSS Python environment (.venv)..." -ForegroundColor Yellow
$VenvDir = Join-Path $BaseDir ".venv"
if (-not (Test-Path $VenvDir)) {
    python -m venv $VenvDir
}
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"
& $VenvPip install -q --upgrade pip
& $VenvPip install -q psycopg2-binary qdrant-client requests

Write-Host "`n[*] Configuring OpenVINO / IPEX-LLM Python environment (.venv-openvino)..." -ForegroundColor Yellow
$VenvOvDir = Join-Path $BaseDir ".venv-openvino"
if (-not (Test-Path $VenvOvDir)) {
    python -m venv $VenvOvDir
}
$VenvOvPip = Join-Path $VenvOvDir "Scripts\pip.exe"
$VenvOvPy = Join-Path $VenvOvDir "Scripts\python.exe"

& $VenvOvPip install -q --upgrade pip

# Check if PyTorch XPU is already installed
$HasXpuTorch = & $VenvOvPy -c 'import torch; print("+xpu" in torch.__version__)' 2>$null
if ($HasXpuTorch -ne "True") {
    Write-Host "[*] Installing PyTorch with Intel Arc XPU support for Windows..." -ForegroundColor Yellow
    & $VenvOvPip install --pre --upgrade torch torchvision torchaudio --index-url https://download.pytorch.org/whl/xpu
} else {
    Write-Host "[✓] PyTorch XPU is already installed." -ForegroundColor Green
}

# Install IPEX-LLM and pinned transformers
Write-Host "[*] Installing IPEX-LLM and supporting runtime dependencies..." -ForegroundColor Yellow
& $VenvOvPip install --pre --upgrade ipex-llm --no-deps
& $VenvOvPip install "transformers>=4.37.0,<=4.44.2" accelerate sentencepiece protobuf torchvision fastapi uvicorn numpy requests pydantic huggingface_hub
& $VenvOvPip install openvino openvino-genai optimum-intel nncf

# 5. Install Qdrant Native Windows Binary
if (-not $SkipQdrant) {
    $QdrantExe = Join-Path $BaseDir "bin\qdrant\qdrant.exe"
    if (-not (Test-Path $QdrantExe)) {
        Write-Host "`n[*] Downloading native Windows Qdrant release..." -ForegroundColor Yellow
        $TmpZip = Join-Path $env:TEMP "qdrant_windows.zip"
        $QdrantReleaseUrl = "https://github.com/qdrant/qdrant/releases/latest/download/qdrant-x86_64-pc-windows-msvc.zip"
        try {
            Invoke-WebRequest -Uri $QdrantReleaseUrl -OutFile $TmpZip
            Expand-Archive -Path $TmpZip -DestinationPath (Join-Path $BaseDir "bin\qdrant") -Force
            Remove-Item $TmpZip -Force -ErrorAction SilentlyContinue
            Write-Host "[✓] Qdrant Windows binary installed: $QdrantExe" -ForegroundColor Green
        } catch {
            Write-Host "[-] Failed to auto-download Qdrant. You can manually place qdrant.exe in .\bin\qdrant\" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[✓] Qdrant binary already present: $QdrantExe" -ForegroundColor Green
    }
}

# 6. Install Node.js packages and build React portal
if (-not $SkipNpm) {
    Write-Host "`n[*] Installing React dependencies and building portal..." -ForegroundColor Yellow
    npm install
    npm run build
}

# 7. Hardware & IPEX Verification
Write-Host "`n[*] Testing Intel Arc GPU (XPU) & IPEX-LLM on Windows..." -ForegroundColor Cyan
& $VenvOvPy -c @"
import os
os.environ.setdefault('ZE_INIT_ALL_DRIVER_TYPES_ENABLE', '1')
os.environ.setdefault('ONEAPI_DEVICE_SELECTOR', 'level_zero:*')
import torch
print('PyTorch Version:', torch.__version__)
xpu = hasattr(torch, 'xpu') and torch.xpu.is_available()
count = torch.xpu.device_count() if xpu else 0
print('Intel Arc GPU (XPU) Available:', '[✓] YES' if xpu else '[-] NO')
print('Intel Arc GPU Device Count:', count)
if count > 0:
    print('GPU Device Name:', torch.xpu.get_device_name(0))
try:
    import ipex_llm
    from ipex_llm.transformers import AutoModelForCausalLM
    print('IPEX-LLM Package: [✓] READY (version ' + str(ipex_llm.__version__) + ')')
except Exception as e:
    print('[-] IPEX-LLM import warning:', e)
"@

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "  Installation Complete!                                 " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "To start the AI Hub on Windows:"
Write-Host "  - Double-click:   start-all.bat"
Write-Host "  - Or PowerShell:  .\scripts\windows\k13ctl.ps1 start all"
Write-Host "  - Status check:   .\scripts\windows\k13ctl.ps1 status"
Write-Host "  - Hardware check: .\scripts\windows\k13ctl.ps1 check-hardware"
Write-Host "  - Web Portal:     http://localhost:3000"
