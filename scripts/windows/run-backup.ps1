# ==============================================================================
# K13 AI Hub - Windows Qdrant & PostgreSQL Daily Backup Runner (4:00 AM Daily)
# Reads BACKUP_PATH from .env (defaults to C:\fetch42\space)
# ==============================================================================
param(
    [switch]$Once = $false
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BaseDir = Resolve-Path "$ScriptDir\..\.."
Set-Location $BaseDir

$Py = Join-Path $BaseDir ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    $Py = "python.exe"
}

$BackupScript = Join-Path $BaseDir "backup\backup_k13.py"
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
    if (-not $env:BACKUP_PATH) {
        $env:BACKUP_PATH = "C:\fetch42\space"
    }
    $qPort = if ($env:QDRANT_PORT) { $env:QDRANT_PORT } else { "6333" }
    $env:QDRANT_HOST = "127.0.0.1"
    $env:QDRANT_PORT = $qPort
    $env:PYTHONUNBUFFERED = "1"
    $env:PYTHONUTF8 = "1"
}

Load-DotEnv

if (-not (Test-Path $env:BACKUP_PATH)) {
    New-Item -ItemType Directory -Path $env:BACKUP_PATH -Force | Out-Null
}

if ($Once) {
    Write-Host "[*] Running immediate Qdrant + PostgreSQL backup to $($env:BACKUP_PATH)..." -ForegroundColor Cyan
    & $Py -u $BackupScript --once
} else {
    Write-Host "[+] Starting K13 Daily 4:00 AM Backup Service (Target: $($env:BACKUP_PATH))..." -ForegroundColor Cyan
    & $Py -u $BackupScript
}

