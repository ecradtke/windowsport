# ==============================================================================
# K13 AI Hub - Windows FreshRSS to Qdrant Sync Runner
# Runs on a 5-minute interval by default (or once when -Once is specified)
# ==============================================================================
param(
    [switch]$Once = $false,
    [int]$IntervalSeconds = 300
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BaseDir = Resolve-Path "$ScriptDir\..\.."
Set-Location $BaseDir

$Py = Join-Path $BaseDir ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    $Py = "python.exe"
}

$SyncScript = Join-Path $BaseDir "rss\sync_freshrss.py"
$EnvFile = Join-Path $BaseDir ".env"

function Load-DotEnv {
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
    $ovPort = if ($env:OV_PORT) { $env:OV_PORT } else { "11434" }
    $qPort = if ($env:QDRANT_PORT) { $env:QDRANT_PORT } else { "6333" }
    $env:EMBEDDING_HOST = "http://127.0.0.1:$ovPort"
    $env:OLLAMA_HOST = "http://127.0.0.1:$ovPort"
    $env:QDRANT_HOST = "127.0.0.1"
    $env:QDRANT_PORT = $qPort
    $env:PYTHONUNBUFFERED = "1"
    $env:PYTHONUTF8 = "1"
}

if ($Once) {
    Load-DotEnv
    Write-Host "[*] Executing one-shot FreshRSS -> PostgreSQL -> Qdrant vector sync on Windows..." -ForegroundColor Yellow
    & $Py $SyncScript
} else {
    Write-Host "[+] Starting FreshRSS -> PostgreSQL -> Qdrant sync loop (every $IntervalSeconds seconds)..." -ForegroundColor Cyan
    while ($true) {
        Load-DotEnv
        Write-Host "[*] [$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Running FreshRSS vector sync..." -ForegroundColor Yellow
        & $Py $SyncScript
        Start-Sleep -Seconds $IntervalSeconds
    }
}
