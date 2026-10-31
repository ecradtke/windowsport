# ==============================================================================
# K13 AI Hub - Windows Control CLI (PowerShell)
# Usage:
#   .\k13ctl.ps1 status
#   .\k13ctl.ps1 start {all|openvino|qdrant|web|rss}
#   .\k13ctl.ps1 stop {all|openvino|qdrant|web|rss}
#   .\k13ctl.ps1 restart {all|openvino|qdrant|web|rss}
#   .\k13ctl.ps1 logs {openvino|qdrant|web|rss}
#   .\k13ctl.ps1 check-hardware
#   .\k13ctl.ps1 fix-transformers
#   .\k13ctl.ps1 test
# ==============================================================================
param(
    [Parameter(Position=0)]
    [string]$Command = "status",

    [Parameter(Position=1)]
    [string]$Target = "all"
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BaseDir = Resolve-Path "$ScriptDir\..\.."
Set-Location $BaseDir

$PidDir = Join-Path $BaseDir "data\pids"
if (-not (Test-Path $PidDir)) {
    New-Item -ItemType Directory -Path $PidDir -Force | Out-Null
}

$LogDir = Join-Path $BaseDir "logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

function Get-ServicePid($name) {
    $pidFile = Join-Path $PidDir "$name.pid"
    if (Test-Path $pidFile) {
        $id = Get-Content $pidFile -ErrorAction SilentlyContinue
        if ($id -and (Get-Process -Id $id -ErrorAction SilentlyContinue)) {
            return [int]$id
        }
    }
    return $null
}

function Save-ServicePid($name, $id) {
    $pidFile = Join-Path $PidDir "$name.pid"
    Set-Content -Path $pidFile -Value $id
}

function Remove-ServicePid($name) {
    $pidFile = Join-Path $PidDir "$name.pid"
    if (Test-Path $pidFile) {
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
}

function Start-K13Service($svc) {
    $existing = Get-ServicePid $svc
    if ($existing) {
        Write-Host "[$svc] Already running (PID: $existing)" -ForegroundColor Yellow
        return
    }

    $logFile = Join-Path $LogDir "$svc.log"
    Write-Host "[+] Starting $svc..." -ForegroundColor Cyan

    switch ($svc) {
        "qdrant" {
            $runner = Join-Path $BaseDir "scripts\windows\run-qdrant.ps1"
            $p = Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$runner`"" -RedirectStandardOutput $logFile -RedirectStandardError (Join-Path $LogDir "qdrant_err.log") -PassThru -WindowStyle Hidden
            Save-ServicePid "qdrant" $p.Id
            Write-Host "[OK] Qdrant started (PID: $($p.Id))" -ForegroundColor Green
        }
        "openvino" {
            $runner = Join-Path $BaseDir "scripts\windows\run-openvino.ps1"
            $p = Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$runner`"" -RedirectStandardOutput $logFile -RedirectStandardError (Join-Path $LogDir "openvino_err.log") -PassThru -WindowStyle Hidden
            Save-ServicePid "openvino" $p.Id
            Write-Host "[OK] OpenVINO / IPEX-LLM started (PID: $($p.Id))" -ForegroundColor Green
        }
        "web" {
            $runner = Join-Path $BaseDir "scripts\windows\run-web.ps1"
            $p = Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$runner`"" -RedirectStandardOutput $logFile -RedirectStandardError (Join-Path $LogDir "web_err.log") -PassThru -WindowStyle Hidden
            Save-ServicePid "web" $p.Id
            Write-Host "[OK] Web portal started (PID: $($p.Id))" -ForegroundColor Green
        }
        "rss" {
            $runner = Join-Path $BaseDir "scripts\windows\run-rss-sync.ps1"
            $p = Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$runner`"" -RedirectStandardOutput $logFile -RedirectStandardError (Join-Path $LogDir "rss_err.log") -PassThru -WindowStyle Hidden
            Save-ServicePid "rss" $p.Id
            Write-Host "[OK] RSS Sync job started (PID: $($p.Id))" -ForegroundColor Green
        }
        default {
            Write-Host "Unknown service: $svc" -ForegroundColor Red
        }
    }
}

function Stop-K13Service($svc) {
    $id = Get-ServicePid $svc
    if ($id) {
        Write-Host "[-] Stopping $svc (PID: $id)..." -ForegroundColor Yellow
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
        Remove-ServicePid $svc
        Write-Host "[OK] $svc stopped." -ForegroundColor Green
    } else {
        # Fallback process search
        switch ($svc) {
            "qdrant" { Stop-Process -Name "qdrant" -Force -ErrorAction SilentlyContinue }
            default {}
        }
        Remove-ServicePid $svc
        Write-Host "[$svc] Not running or already stopped." -ForegroundColor DarkGray
    }
}

switch ($Command.ToLower()) {
    "status" {
        Write-Host "==========================================================" -ForegroundColor Cyan
        Write-Host "  K13 AI Hub - Windows Services Status                    " -ForegroundColor Cyan
        Write-Host "==========================================================" -ForegroundColor Cyan

        $services = @("qdrant", "openvino", "web")
        foreach ($s in $services) {
            $pidVal = Get-ServicePid $s
            $stat = if ($pidVal) { "[ACTIVE] PID: $pidVal" } else { "[STOPPED]" }
            $color = if ($pidVal) { "Green" } else { "DarkGray" }
            Write-Host ("{0,-12} {1}" -f $s, $stat) -ForegroundColor $color
        }

        Write-Host "`n--- Health Checks ---" -ForegroundColor Yellow
        # Qdrant probe
        try {
            $qRes = Invoke-RestMethod -Uri "http://127.0.0.1:6333/healthz" -TimeoutSec 3 -ErrorAction Stop
            Write-Host "Qdrant    : [OK] HTTP 200 OK -> http://localhost:6333/dashboard" -ForegroundColor Green
        } catch {
            Write-Host "Qdrant    : [-] Not responding (http://127.0.0.1:6333)" -ForegroundColor Red
        }

        # OpenVINO probe
        try {
            $ovRes = Invoke-RestMethod -Uri "http://127.0.0.1:11434/healthz" -TimeoutSec 5 -ErrorAction Stop
            Write-Host "OpenVINO  : [OK] Status: $($ovRes.status) | LLM: $($ovRes.llm_hardware) ($($ovRes.current_model)) | Embeddings: $($ovRes.embed_hardware)" -ForegroundColor Green
        } catch {
            Write-Host "OpenVINO  : [-] Not responding (still loading model onto Intel Arc GPU?)" -ForegroundColor Yellow
        }

        # Web portal probe
        try {
            $wRes = Invoke-WebRequest -Uri "http://localhost:3000" -TimeoutSec 3 -ErrorAction Stop
            Write-Host "Web Portal: [OK] HTTP 200 OK -> http://localhost:3000" -ForegroundColor Green
        } catch {
            Write-Host "Web Portal: [-] Not responding (http://localhost:3000)" -ForegroundColor DarkGray
        }
    }

    "start" {
        if ($Target -eq "all") {
            Start-K13Service "qdrant"
            Start-Sleep -Seconds 1
            Start-K13Service "openvino"
            Start-Sleep -Seconds 1
            Start-K13Service "web"
        } else {
            Start-K13Service $Target
        }
    }

    "stop" {
        if ($Target -eq "all") {
            Stop-K13Service "web"
            Stop-K13Service "openvino"
            Stop-K13Service "qdrant"
            Stop-K13Service "rss"
        } else {
            Stop-K13Service $Target
        }
    }

    "restart" {
        if ($Target -eq "all") {
            & $PSCommandPath stop all
            Start-Sleep -Seconds 2
            & $PSCommandPath start all
        } else {
            Stop-K13Service $Target
            Start-Sleep -Seconds 1
            Start-K13Service $Target
        }
    }

    "logs" {
        $svc = if ($Target -and $Target -ne "all") { $Target } else { "openvino" }
        $logPath = Join-Path $LogDir "$svc.log"
        if (Test-Path $logPath) {
            Get-Content $logPath -Tail 60 -Wait
        } else {
            Write-Host "No log file found at $logPath" -ForegroundColor Yellow
        }
    }

    "check-hardware" {
        $Py = Join-Path $BaseDir ".venv-openvino\Scripts\python.exe"
        if (-not (Test-Path $Py)) { $Py = "python.exe" }
        $verifyScript = Join-Path $BaseDir "scripts\windows\verify_hardware.py"
        if (Test-Path $verifyScript) {
            & $Py $verifyScript
        } else {
            Write-Host "[-] Verification script not found at $verifyScript" -ForegroundColor Red
        }
    }

    "fix-transformers" {
        $Pip = Join-Path $BaseDir ".venv-openvino\Scripts\pip.exe"
        Write-Host "[*] Pinning transformers<=4.44.2 to resolve OffloadedCache issue..." -ForegroundColor Yellow
        $fixArgs = @("install", "transformers>=4.37.0,<=4.44.2")
        & $Pip @fixArgs
        Write-Host "[OK] Done! Verifying IPEX-LLM..." -ForegroundColor Green
        & $PSCommandPath check-hardware
    }

    "test" {
        Write-Host "[*] Running embedding test..." -ForegroundColor Cyan
        try {
            $body = '{"prompt":"High-NA EUV lithography"}'
            $res = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/embeddings" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 15
            Write-Host "  Embedding Dimensions: $($res.embedding.Length)" -ForegroundColor Green
        } catch {
            Write-Host "  [-] Embedding test failed: $_" -ForegroundColor Red
        }

        Write-Host "[*] Running chat generation test..." -ForegroundColor Cyan
        try {
            $body = '{"prompt":"Reply with the single word: ready","stream":false}'
            $res = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/generate" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 30
            Write-Host "  Chat Response: $($res.response.Trim())" -ForegroundColor Green
        } catch {
            Write-Host "  [-] Chat test failed: $_" -ForegroundColor Red
        }
    }

    "install-qdrant-ui" {
        $StaticDir = Join-Path $BaseDir "bin\qdrant\static"
        Write-Host "[*] Downloading Qdrant Web Dashboard (Web GUI)..." -ForegroundColor Yellow
        $TmpUiZip = Join-Path $env:TEMP "qdrant_ui.zip"
        $UiReleaseUrl = "https://github.com/qdrant/qdrant-web-ui/releases/latest/download/dist-qdrant.zip"
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $UiReleaseUrl -OutFile $TmpUiZip -UseBasicParsing
            $TmpExtractDir = Join-Path $env:TEMP "qdrant_ui_extracted"
            if (Test-Path $TmpExtractDir) { Remove-Item $TmpExtractDir -Recurse -Force -ErrorAction SilentlyContinue }
            Expand-Archive -Path $TmpUiZip -DestinationPath $TmpExtractDir -Force

            if (-not (Test-Path $StaticDir)) {
                New-Item -ItemType Directory -Path $StaticDir -Force | Out-Null
            }

            $DistSubDir = Join-Path $TmpExtractDir "dist"
            if (Test-Path $DistSubDir) {
                Copy-Item -Path "$DistSubDir\*" -Destination $StaticDir -Recurse -Force
            } else {
                Copy-Item -Path "$TmpExtractDir\*" -Destination $StaticDir -Recurse -Force
            }

            Remove-Item $TmpUiZip -Force -ErrorAction SilentlyContinue
            Remove-Item $TmpExtractDir -Recurse -Force -ErrorAction SilentlyContinue
            Write-Host "[OK] Qdrant Web Dashboard installed at $StaticDir" -ForegroundColor Green
            Write-Host "Restarting Qdrant service..." -ForegroundColor Cyan
            & $PSCommandPath restart qdrant
        } catch {
            Write-Host "[-] Could not download Qdrant Web Dashboard: $_" -ForegroundColor Red
        }
    }

    default {
        Write-Host "Usage: .\k13ctl.ps1 {status|start|stop|restart|logs|check-hardware|fix-transformers|install-qdrant-ui|test} [target]" -ForegroundColor Yellow
    }
}
