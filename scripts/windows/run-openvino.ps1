# ==============================================================================
# K13 AI Hub - Windows OpenVINO / IPEX-LLM Server Runner
# Launches FastAPI server with Intel Arc GPU (XPU) & Intel NPU embedding support
# ==============================================================================
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BaseDir = Resolve-Path "$ScriptDir\..\.."
Set-Location $BaseDir

# Load .env if present
$EnvFile = Join-Path $BaseDir ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            $k = $parts[0].Trim()
            $v = $parts[1].Trim().Trim('"').Trim("'")
            if ($k -and $v) {
                [System.Environment]::SetEnvironmentVariable($k, $v, "Process")
            }
        }
    }
}

# Optional OpenVINO setupvars.bat if configured
if ($env:OPENVINO_SETUPVARS -and (Test-Path $env:OPENVINO_SETUPVARS)) {
    Write-Host "[*] Loading OpenVINO environment from $($env:OPENVINO_SETUPVARS)..." -ForegroundColor Yellow
    cmd.exe /c "`"$($env:OPENVINO_SETUPVARS)`" && set" | ForEach-Object {
        if ($_ -match "^([^=]+)=(.*)$") {
            [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
}

# Python selection
$Py = [System.Environment]::GetEnvironmentVariable("OPENVINO_PYTHON")
if (-not $Py -or -not (Test-Path $Py)) {
    $Py = Join-Path $BaseDir ".venv-openvino\Scripts\python.exe"
}
if (-not (Test-Path $Py)) {
    $Py = "python.exe"
}

# Environment defaults & .env mappings
if (-not $env:DEFAULT_MODEL) { $env:DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct" }
if (-not $env:EMBED_MODEL) { $env:EMBED_MODEL = "BAAI/bge-base-en-v1.5" }
if (-not $env:LLM_DEVICE) { $env:LLM_DEVICE = "GPU" }
if (-not $env:EMBED_DEVICE) { $env:EMBED_DEVICE = "NPU" }
if (-not $env:MAX_NEW_TOKENS) { $env:MAX_NEW_TOKENS = "2048" }
if (-not $env:SERVER_HOST) { $env:SERVER_HOST = if ($env:OV_HOST) { $env:OV_HOST } else { "0.0.0.0" } }
if (-not $env:SERVER_PORT) { $env:SERVER_PORT = if ($env:OV_PORT) { $env:OV_PORT } else { "11434" } }

# Intel oneAPI and Level Zero optimizations for Windows Intel Arc & NPU
$env:ZE_INIT_ALL_DRIVER_TYPES_ENABLE = "1"
$env:ONEAPI_DEVICE_SELECTOR = "level_zero:*"
$env:SYCL_CACHE_PERSISTENT = "1"
$env:SYCL_PI_LEVEL_ZERO_USE_IMMEDIATE_COMMANDLISTS = "1"
$env:ZE_ENABLE_PCI_ID_DEVICE_ORDER = "1"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONUTF8 = "1"

# Storage
if (-not $env:MODELS_DIR) {
    if ($env:OV_MODELS_DIR) {
        $env:MODELS_DIR = $env:OV_MODELS_DIR
    } elseif ($env:K13_DATA_DIR) {
        $env:MODELS_DIR = Join-Path $env:K13_DATA_DIR "models"
    } else {
        $env:MODELS_DIR = Join-Path $BaseDir "data\models"
    }
}
if (-not (Test-Path $env:MODELS_DIR)) {
    New-Item -ItemType Directory -Path $env:MODELS_DIR -Force | Out-Null
}

$ServerScript = Join-Path $BaseDir "openvino\server.py"
Write-Host "[+] Starting K13 IPEX-LLM server on Windows: http://$($env:SERVER_HOST):$($env:SERVER_PORT)" -ForegroundColor Cyan
& $Py $ServerScript
