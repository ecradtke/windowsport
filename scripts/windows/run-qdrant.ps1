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

$DataRoot = if ($env:K13_DATA_DIR) { $env:K13_DATA_DIR } else { Join-Path $BaseDir "data" }
$StorageDir = if ($env:QDRANT_STORAGE_DIR) { $env:QDRANT_STORAGE_DIR } else { Join-Path $DataRoot "qdrant\storage" }
$SnapshotsDir = if ($env:QDRANT_SNAPSHOTS_DIR) { $env:QDRANT_SNAPSHOTS_DIR } else { Join-Path $DataRoot "qdrant\snapshots" }
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

$Port = if ($env:QDRANT_PORT -and ($env:QDRANT_PORT -match '^\d+$')) { $env:QDRANT_PORT } else { "6333" }
$HostBind = if ($env:QDRANT_BIND) { $env:QDRANT_BIND } else { "0.0.0.0" }

$env:QDRANT__STORAGE__STORAGE_PATH = $StorageDir
$env:QDRANT__STORAGE__SNAPSHOTS_PATH = $SnapshotsDir
$env:QDRANT__STORAGE__ON_DISK_PAYLOAD = "true"
$env:QDRANT__STORAGE__OPTIMIZERS__DEFAULT_SEGMENT_NUMBER = "2"
$env:QDRANT__STORAGE__OPTIMIZERS__MAX_OPTIMIZATION_THREADS = "1"
$env:QDRANT__STORAGE__OPTIMIZERS__MEMMAP_THRESHOLD_KB = "10240"
$env:QDRANT__STORAGE__OPTIMIZERS__INDEXING_THRESHOLD_KB = "20480"
$env:QDRANT__STORAGE__PERFORMANCE__MAX_SEARCH_THREADS = "2"
$env:QDRANT__STORAGE__WAL__WAL_CAPACITY_MB = "16"
$env:QDRANT__SERVICE__HOST = $HostBind
$env:QDRANT__SERVICE__HTTP_PORT = $Port
$env:QDRANT__SERVICE__GRPC_PORT = "6334"
$env:QDRANT__SERVICE__ENABLE_CORS = "true"
$env:QDRANT__SERVICE__ENABLE_STATIC_CONTENT = "true"
$env:QDRANT__SERVICE__STATIC_CONTENT_DIR = $StaticDir
$env:QDRANT__SERVICE__MAX_REQUEST_SIZE_MB = "32"
$env:QDRANT__TELEMETRY_DISABLED = "true"

Write-Host "[+] Starting Qdrant vector database on Windows: http://$($HostBind):$Port (Web GUI: http://$($HostBind):$Port/dashboard)" -ForegroundColor Green
& $QdrantBin
