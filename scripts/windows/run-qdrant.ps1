# ==============================================================================
# K13 AI Hub - Windows Qdrant Vector Database Runner
# ==============================================================================
$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BaseDir = Resolve-Path "$ScriptDir\..\.."
Set-Location $BaseDir

$QdrantBin = Join-Path $BaseDir "bin\qdrant\qdrant.exe"
if (-not (Test-Path $QdrantBin)) {
    Write-Host "[-] Qdrant binary not found at $QdrantBin. Run .\scripts\windows\install.ps1 first." -ForegroundColor Red
    exit 1
}

$StorageDir = Join-Path $BaseDir "data\qdrant\storage"
$SnapshotsDir = Join-Path $BaseDir "data\qdrant\snapshots"
$StaticDir = Join-Path $BaseDir "bin\qdrant\static"

if (-not (Test-Path $StorageDir)) { New-Item -ItemType Directory -Path $StorageDir -Force | Out-Null }
if (-not (Test-Path $SnapshotsDir)) { New-Item -ItemType Directory -Path $SnapshotsDir -Force | Out-Null }
if (-not (Test-Path $StaticDir)) { New-Item -ItemType Directory -Path $StaticDir -Force | Out-Null }

# Ensure Qdrant Web UI Dashboard (GUI) is present
$IndexHtml = Join-Path $StaticDir "index.html"
if (-not (Test-Path $IndexHtml)) {
    Write-Host "[*] Qdrant Web Dashboard not found. Downloading latest Web GUI..." -ForegroundColor Yellow
    $TmpUiZip = Join-Path $env:TEMP "qdrant_ui.zip"
    $UiReleaseUrl = "https://github.com/qdrant/qdrant-web-ui/releases/latest/download/dist-qdrant.zip"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $UiReleaseUrl -OutFile $TmpUiZip -UseBasicParsing
        $TmpExtractDir = Join-Path $env:TEMP "qdrant_ui_extracted"
        if (Test-Path $TmpExtractDir) { Remove-Item $TmpExtractDir -Recurse -Force -ErrorAction SilentlyContinue }
        Expand-Archive -Path $TmpUiZip -DestinationPath $TmpExtractDir -Force

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
}

$Port = "6333"
$HostBind = "0.0.0.0"

$EnvFile = Join-Path $BaseDir ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line.StartsWith("QDRANT_PORT=")) {
            $val = $line.Split("=", 2)[1].Trim().Trim('"').Trim("'")
            if ($val -and ($val -match '^\d+$')) { $Port = $val }
        }
        if ($line.StartsWith("QDRANT_BIND=")) {
            $val = $line.Split("=", 2)[1].Trim().Trim('"').Trim("'")
            if ($val) { $HostBind = $val }
        }
    }
}

$env:QDRANT__STORAGE__STORAGE_PATH = $StorageDir
$env:QDRANT__STORAGE__SNAPSHOTS_PATH = $SnapshotsDir
$env:QDRANT__SERVICE__HOST = $HostBind
$env:QDRANT__SERVICE__HTTP_PORT = $Port
$env:QDRANT__SERVICE__GRPC_PORT = "6334"
$env:QDRANT__SERVICE__ENABLE_CORS = "true"
$env:QDRANT__SERVICE__ENABLE_STATIC_CONTENT = "true"
$env:QDRANT__SERVICE__STATIC_CONTENT_DIR = $StaticDir
$env:QDRANT__SERVICE__MAX_REQUEST_SIZE_MB = "64"
$env:QDRANT__TELEMETRY_DISABLED = "true"

Write-Host "[+] Starting Qdrant vector database on Windows: http://$($HostBind):$Port (Web GUI: http://$($HostBind):$Port/dashboard)" -ForegroundColor Green
& $QdrantBin
