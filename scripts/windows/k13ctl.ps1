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
            Write-Host "[✓] Qdrant started (PID: $($p.Id))" -ForegroundColor Green
        }
        "openvino" {
            $runner = Join-Path $BaseDir "scripts\windows\run-openvino.ps1"
            $p = Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$runner`"" -RedirectStandardOutput $logFile -RedirectStandardError (Join-Path $LogDir "openvino_err.log") -PassThru -WindowStyle Hidden
            Save-ServicePid "openvino" $p.Id
            Write-Host "[✓] OpenVINO / IPEX-LLM started (PID: $($p.Id))" -ForegroundColor Green
        }
        "web" {
            $runner = Join-Path $BaseDir "scripts\windows\run-web.ps1"
            $p = Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$runner`"" -RedirectStandardOutput $logFile -RedirectStandardError (Join-Path $LogDir "web_err.log") -PassThru -WindowStyle Hidden
            Save-ServicePid "web" $p.Id
            Write-Host "[✓] Web portal started (PID: $($p.Id))" -ForegroundColor Green
        }
        "rss" {
            $runner = Join-Path $BaseDir "scripts\windows\run-rss-sync.ps1"
            $p = Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$runner`"" -RedirectStandardOutput $logFile -RedirectStandardError (Join-Path $LogDir "rss_err.log") -PassThru -WindowStyle Hidden
            Save-ServicePid "rss" $p.Id
            Write-Host "[✓] RSS Sync job started (PID: $($p.Id))" -ForegroundColor Green
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
        Write-Host "[✓] $svc stopped." -ForegroundColor Green
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
            Write-Host "Qdrant    : [✓] HTTP 200 OK (Vector DB responsive)" -ForegroundColor Green
        } catch {
            Write-Host "Qdrant    : [-] Not responding (http://127.0.0.1:6333)" -ForegroundColor Red
        }

        # OpenVINO probe
        try {
            $ovRes = Invoke-RestMethod -Uri "http://127.0.0.1:11434/healthz" -TimeoutSec 5 -ErrorAction Stop
            Write-Host "OpenVINO  : [✓] Status: $($ovRes.status) | LLM: $($ovRes.llm_hardware) ($($ovRes.current_model)) | Embeddings: $($ovRes.embed_hardware)" -ForegroundColor Green
        } catch {
            Write-Host "OpenVINO  : [-] Not responding (still loading model onto Intel Arc GPU?)" -ForegroundColor Yellow
        }

        # Web portal probe
        try {
            $wRes = Invoke-WebRequest -Uri "http://localhost:3000" -TimeoutSec 3 -ErrorAction Stop
            Write-Host "Web Portal: [✓] HTTP 200 OK -> http://localhost:3000" -ForegroundColor Green
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
        Write-Host "[*] Checking Windows Intel Arc GPU (XPU), NPU & IPEX-LLM..." -ForegroundColor Cyan
        & $Py -c @"
import os
os.environ.setdefault('ZE_INIT_ALL_DRIVER_TYPES_ENABLE', '1')
os.environ.setdefault('ONEAPI_DEVICE_SELECTOR', 'level_zero:*')
import torch
print('[*] PyTorch Version:', torch.__version__)
xpu = hasattr(torch, 'xpu') and torch.xpu.is_available()
count = torch.xpu.device_count() if xpu else 0
print('[*] Intel Arc GPU (XPU) Available:', '[✓] YES' if xpu else '[-] NO')
print('[*] Intel Arc GPU Device Count:', count)
if count > 0:
    print('    Device Name:', torch.xpu.get_device_name(0))
else:
    print('[-] Device count is 0. Ensure Intel Arc Graphics Windows 11 WHQL driver is installed.')
try:
    import ipex_llm
    from ipex_llm.transformers import AutoModelForCausalLM
    print('[+] IPEX-LLM Package: [✓] READY (version ' + str(ipex_llm.__version__) + ')')
except Exception as e:
    print('[-] IPEX-LLM Import Warning:', e)
    if 'OffloadedCache' in str(e):
        print('    Tip: Run .\\scripts\\windows\\k13ctl.ps1 fix-transformers to pin transformers<=4.44.2')
try:
    import openvino as ov
    core = ov.Core()
    devs = core.available_devices
    print('[*] OpenVINO Devices Detected:', ', '.join(devs))
    if 'NPU' in devs:
        print('[+] Intel NPU Acceleration: [✓] AVAILABLE')
    else:
        print('[-] Intel NPU not detected in OpenVINO (CPU fallback will be used)')
except Exception as e:
    print('[-] OpenVINO Warning:', e)
"@
    }

    "fix-transformers" {
        $Pip = Join-Path $BaseDir ".venv-openvino\Scripts\pip.exe"
        Write-Host "[*] Pinning transformers<=4.44.2 to resolve OffloadedCache issue..." -ForegroundColor Yellow
        & $Pip install "transformers>=4.37.0,<=4.44.2"
        Write-Host "[✓] Done! Verifying IPEX-LLM..." -ForegroundColor Green
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

    default {
        Write-Host "Usage: .\k13ctl.ps1 {status|start|stop|restart|logs|check-hardware|fix-transformers|test} [target]" -ForegroundColor Yellow
    }
}
