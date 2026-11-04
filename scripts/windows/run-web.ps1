# ==============================================================================
# K13 AI Hub - Windows Pure-Python Web Portal Runner (FastAPI / Uvicorn)
# ==============================================================================
$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BaseDir = Resolve-Path "$ScriptDir\..\.."
Set-Location $BaseDir

# Terminate any legacy Node.js processes from previous Vite runs to free RAM
Stop-Process -Name "node" -Force -ErrorAction SilentlyContinue

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

$Port = if ($env:WEB_PORT -and ($env:WEB_PORT -match '^\d+$')) { $env:WEB_PORT } else { "3000" }
$env:WEB_PORT = $Port

# Select Python from .venv
$Py = Join-Path $BaseDir ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    $Py = "python.exe"
}

$WebServerScript = Join-Path $BaseDir "web\server.py"
Write-Host "[+] Starting K13 Pure-Python Web Portal on Windows: http://localhost:$Port" -ForegroundColor Cyan
& $Py -u $WebServerScript
