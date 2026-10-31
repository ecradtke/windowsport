# ==============================================================================
# K13 AI Hub - Windows llama.cpp Server Runner
# Launches FastAPI orchestrator managing native llama-server.exe & embeddings
# ==============================================================================
$ErrorActionPreference = "Continue"
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

# Python selection & automatic venv bootstrap if missing
$VenvDir = Join-Path $BaseDir ".venv"
$Py = Join-Path $VenvDir "Scripts\python.exe"
$Pip = Join-Path $VenvDir "Scripts\pip.exe"
if (-not (Test-Path $Py)) {
    Write-Host "[*] Creating Python virtual environment (.venv)..." -ForegroundColor Yellow
    & python.exe -m venv $VenvDir
}
if (Test-Path $Py) {
    & $Py -c "import importlib.util, sys; sys.exit(0 if all(importlib.util.find_spec(m) for m in ('fastapi','uvicorn','requests','huggingface_hub','numpy')) else 1)"
    if ($LASTEXITCODE -ne 0) {
        $reqFile = Join-Path $BaseDir "llama\requirements.txt"
        Write-Host "[*] Installing Python dependencies from $reqFile..." -ForegroundColor Yellow
        & $Pip install -r $reqFile
    }
} else {
    $Py = "python.exe"
}

# Environment defaults
if (-not $env:DEFAULT_MODEL) { $env:DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct-GGUF" }
if (-not $env:EMBED_MODEL) { $env:EMBED_MODEL = "BAAI/bge-base-en-v1.5" }
if (-not $env:LLM_DEVICE) { $env:LLM_DEVICE = "GPU" }
if (-not $env:EMBED_DEVICE) { $env:EMBED_DEVICE = "CPU" }
if (-not $env:MAX_NEW_TOKENS) { $env:MAX_NEW_TOKENS = "2048" }
if (-not $env:LLAMA_NGL) { $env:LLAMA_NGL = "99" }
if (-not $env:LLAMA_CTX_SIZE) { $env:LLAMA_CTX_SIZE = "16384" }
if (-not $env:SERVER_HOST) { $env:SERVER_HOST = if ($env:LLAMA_HOST) { $env:LLAMA_HOST } else { "0.0.0.0" } }
if (-not $env:SERVER_PORT) { $env:SERVER_PORT = if ($env:LLAMA_PORT) { $env:LLAMA_PORT } else { "11434" } }

$env:PYTHONUNBUFFERED = "1"
$env:PYTHONUTF8 = "1"

# Models directory
if (-not $env:MODELS_DIR) {
    if ($env:LLAMA_MODELS_DIR) {
        $env:MODELS_DIR = $env:LLAMA_MODELS_DIR
    } elseif ($env:K13_DATA_DIR) {
        $env:MODELS_DIR = Join-Path $env:K13_DATA_DIR "models"
    } else {
        $env:MODELS_DIR = Join-Path $BaseDir "data\models"
    }
}
if (-not (Test-Path $env:MODELS_DIR)) {
    New-Item -ItemType Directory -Path $env:MODELS_DIR -Force | Out-Null
}

$ServerScript = Join-Path $BaseDir "llama\server.py"
Write-Host "[+] Starting K13 llama.cpp server on Windows: http://$($env:SERVER_HOST):$($env:SERVER_PORT)" -ForegroundColor Cyan
& $Py $ServerScript
