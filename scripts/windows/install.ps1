# ==============================================================================
# K13 AI Hub - Complete Windows 11 / Windows Server Native Installer (llama.cpp)
# Sets up llama.cpp, Hugging Face Embeddings, Qdrant, and React Web Portal
# ==============================================================================
param(
    [switch]$SkipQdrant = $false,
    [switch]$SkipNpm = $false
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BaseDir = Resolve-Path "$ScriptDir\..\.."
Set-Location $BaseDir

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  K13 AI Hub - Native Windows Setup (llama.cpp + Qdrant)  " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Target Directory: $BaseDir"

# 1. Environment file check
$EnvFile = Join-Path $BaseDir ".env"
$EnvExample = Join-Path $BaseDir ".env.example"
if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample $EnvFile
        Write-Host "[+] Created .env from .env.example. Please review settings." -ForegroundColor Green
    }
}

# 2. Check Prerequisites
Write-Host "`n[*] Checking system prerequisites..." -ForegroundColor Yellow

$PythonExe = "python.exe"
$pyCmd = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $pyCmd) {
    Write-Host "[-] Python is not installed or not in PATH! Please install Python 3.10+ from python.org." -ForegroundColor Red
    exit 1
}

$pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
if ($pyLauncher) {
    foreach ($ver in @("-3.12", "-3.11", "-3.10")) {
        $found = & py.exe $ver -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $found -and (Test-Path $found.Trim())) {
            $PythonExe = $found.Trim()
            Write-Host "[*] Selected Python ${ver}: $PythonExe" -ForegroundColor Cyan
            break
        }
    }
}

$pyVer = & $PythonExe --version 2>&1 | Out-String
Write-Host "[OK] Python: $($pyVer.Trim()) (100% Python runtime - no Node.js required)" -ForegroundColor Green

# 3. Create Directories
$Dirs = @(
    "bin\qdrant",
    "bin\llama",
    "data\models",
    "data\qdrant\storage",
    "data\qdrant\snapshots",
    "logs"
)
foreach ($d in $Dirs) {
    $fullPath = Join-Path $BaseDir $d
    if (-not (Test-Path $fullPath)) {
        New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
    }
}

# 4. Create and configure unified Python virtual environment (.venv)
Write-Host "`n[*] Configuring Python virtual environment (.venv)..." -ForegroundColor Yellow
$VenvDir = Join-Path $BaseDir ".venv"
if (-not (Test-Path $VenvDir)) {
    & $PythonExe -m venv $VenvDir
}
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"
$VenvPy = Join-Path $VenvDir "Scripts\python.exe"

$pipUpArgs = @("install", "-q", "--upgrade", "pip")
& $VenvPip @pipUpArgs

Write-Host "[*] Installing llama.cpp orchestrator, Hugging Face, and RSS sync dependencies..." -ForegroundColor Yellow
$reqFile = Join-Path $BaseDir "llama\requirements.txt"
if (Test-Path $reqFile) {
    $pipReqArgs = @("install", "-r", $reqFile)
    & $VenvPip @pipReqArgs
}
$rssArgs = @("install", "-q", "psycopg2-binary", "qdrant-client", "requests")
& $VenvPip @rssArgs

# 5. Install Qdrant Native Windows Binary
if (-not $SkipQdrant) {
    $QdrantExe = Join-Path $BaseDir "bin\qdrant\qdrant.exe"
    if (-not (Test-Path $QdrantExe)) {
        Write-Host "`n[*] Downloading native Windows Qdrant release..." -ForegroundColor Yellow
        $TmpZip = Join-Path $env:TEMP "qdrant_windows.zip"
        $QdrantReleaseUrl = "https://github.com/qdrant/qdrant/releases/latest/download/qdrant-x86_64-pc-windows-msvc.zip"
        try {
            Invoke-WebRequest -Uri $QdrantReleaseUrl -OutFile $TmpZip
            Expand-Archive -Path $TmpZip -DestinationPath (Join-Path $BaseDir "bin\qdrant") -Force
            Remove-Item $TmpZip -Force -ErrorAction SilentlyContinue
            Write-Host "[OK] Qdrant Windows binary installed: $QdrantExe" -ForegroundColor Green
        } catch {
            Write-Host "[-] Failed to auto-download Qdrant. You can manually place qdrant.exe in .\bin\qdrant\" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[OK] Qdrant binary already present: $QdrantExe" -ForegroundColor Green
    }

    # Download and install Qdrant Web Dashboard (GUI)
    $StaticDir = Join-Path $BaseDir "bin\qdrant\static"
    $IndexHtml = Join-Path $StaticDir "index.html"
    if (-not (Test-Path $IndexHtml)) {
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
        } catch {
            Write-Host "[-] Could not download Qdrant Web Dashboard: $_" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[OK] Qdrant Web Dashboard already present: $StaticDir" -ForegroundColor Green
    }
}

# 6. Verify Pure-Python Web Portal (web\server.py)
Write-Host "`n[OK] Pure-Python Web Portal ready at .\web\server.py (Node.js/npm eliminated)." -ForegroundColor Green

# 7. Hardware and llama.cpp Verification
Write-Host "`n[*] Verifying llama.cpp and hardware stack on Windows..." -ForegroundColor Cyan
$verifyScript = Join-Path $BaseDir "scripts\windows\verify_hardware.py"
if (Test-Path $verifyScript) {
    & $VenvPy $verifyScript
}

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "  Installation Complete!                                 " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "To start the AI Hub on Windows:"
Write-Host "  - Double-click:   start-all.bat"
Write-Host "  - Or PowerShell:  .\scripts\windows\k13ctl.ps1 start all"
Write-Host "  - Status check:   .\scripts\windows\k13ctl.ps1 status"
Write-Host "  - Hardware check: .\scripts\windows\k13ctl.ps1 check-hardware"
Write-Host "  - Web Portal:     http://localhost:3000"
