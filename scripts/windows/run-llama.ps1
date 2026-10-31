# ==============================================================================
# K13 AI Hub - Windows llama.cpp Server Runner
# Launches FastAPI orchestrator managing native llama-server.exe (GPU) & NPU embeddings
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

# Helper to locate Python 3.12 / 3.11 / 3.13 (required for Intel NPU wheels on Windows)
function Get-CompatiblePython {
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        foreach ($v in @("-3.12", "-3.13", "-3.11", "-3.10")) {
            $p = & py.exe $v -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $p -and (Test-Path $p.Trim())) {
                return $p.Trim()
            }
        }
    }
    $searchPaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "C:\Python312\python.exe",
        "C:\Program Files\Python312\python.exe"
    )
    foreach ($sp in $searchPaths) {
        if (Test-Path $sp) { return $sp }
    }
    return "python.exe"
}

$VenvDir = Join-Path $BaseDir ".venv"
$Py = Join-Path $VenvDir "Scripts\python.exe"
$Pip = Join-Path $VenvDir "Scripts\pip.exe"

# Recreate .venv if it was created with Python 3.14/3.15 (which lacks Intel NPU wheels)
if (Test-Path $Py) {
    & $Py -c "import sys; sys.exit(0 if sys.version_info < (3, 14) else 1)"
    if ($LASTEXITCODE -ne 0) {
        $compatPy = Get-CompatiblePython
        if ($compatPy -ne "python.exe") {
            Write-Host "[*] Upgrading .venv to $compatPy for Intel NPU driver support..." -ForegroundColor Yellow
            Remove-Item $VenvDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

if (-not (Test-Path $Py)) {
    $compatPy = Get-CompatiblePython
    Write-Host "[*] Creating Python virtual environment (.venv) using $compatPy..." -ForegroundColor Yellow
    & $compatPy -m venv $VenvDir
}

if (Test-Path $Py) {
    & $Py -c "import importlib.util, sys; sys.exit(0 if all(importlib.util.find_spec(m) for m in ('fastapi','uvicorn','requests','huggingface_hub','numpy','tokenizers','openvino')) else 1)"
    if ($LASTEXITCODE -ne 0) {
        $reqFile = Join-Path $BaseDir "llama\requirements.txt"
        Write-Host "[*] Installing Python dependencies from $reqFile..." -ForegroundColor Yellow
        & $Pip install -r $reqFile
    }
} else {
    $Py = "python.exe"
}

# Environment defaults (LLM on GPU via llama.cpp, Embeddings always on Intel NPU)
if (-not $env:DEFAULT_MODEL) { $env:DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct-GGUF" }
if (-not $env:EMBED_MODEL) { $env:EMBED_MODEL = "BAAI/bge-base-en-v1.5" }
if (-not $env:LLM_DEVICE) { $env:LLM_DEVICE = "GPU" }
$env:EMBED_DEVICE = "NPU"
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
Write-Host "[+] Starting K13 llama.cpp server on Windows: http://$($env:SERVER_HOST):$($env:SERVER_PORT) (LLM: GPU, Embeddings: NPU)" -ForegroundColor Cyan
& $Py $ServerScript
