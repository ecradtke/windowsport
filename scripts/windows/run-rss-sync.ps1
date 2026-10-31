# ==============================================================================
# K13 AI Hub - Windows FreshRSS to Qdrant Sync Runner
# ==============================================================================
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BaseDir = Resolve-Path "$ScriptDir\..\.."
Set-Location $BaseDir

$Py = Join-Path $BaseDir ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    $Py = "python.exe"
}

$SyncScript = Join-Path $BaseDir "rss\sync_freshrss.py"
Write-Host "[*] Executing FreshRSS -> PostgreSQL -> Qdrant vector sync on Windows..." -ForegroundColor Yellow
& $Py $SyncScript
