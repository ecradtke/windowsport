# ==============================================================================
# K13 AI Hub - Windows Web Portal Runner
# ==============================================================================
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BaseDir = Resolve-Path "$ScriptDir\..\.."
Set-Location $BaseDir

# Default port
$Port = "3000"

# Load .env if present
$EnvFile = Join-Path $BaseDir ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line.StartsWith("WEB_PORT=")) {
            $val = $line.Split("=", 2)[1].Trim().Trim('"').Trim("'")
            if ($val -and ($val -match '^\d+$')) {
                $Port = $val
            }
        }
    }
}

Write-Host "[+] Starting K13 Web Portal on Windows: http://localhost:$Port" -ForegroundColor Cyan

if ($Port -ne "3000") {
    npm run dev -- --port $Port --host 0.0.0.0
} else {
    npm run dev
}
