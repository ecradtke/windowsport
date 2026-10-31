# ==============================================================================
# K13 AI Hub - Windows Web Portal Runner
# ==============================================================================
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BaseDir = Resolve-Path "$ScriptDir\..\.."
Set-Location $BaseDir

# Load .env if present
$EnvFile = Join-Path $BaseDir ".env"
$Port = "3000"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line.StartsWith("WEB_PORT=")) {
            $Port = $line.Split("=", 2)[1].Trim().Trim('"')
        }
    }
}

Write-Host "[+] Starting K13 Web Portal on Windows: http://localhost:$Port" -ForegroundColor Cyan
npm run dev -- --port $Port --host 0.0.0.0
