# ==============================================================================
# K13 AI Hub - Windows Qdrant Vector Database Runner
# ==============================================================================
$ErrorActionPreference = "Stop"
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

New-Item -ItemType Directory -Path $StorageDir -Force | Out-Null
New-Item -ItemType Directory -Path $SnapshotsDir -Force | Out-Null

$env:QDRANT__STORAGE__STORAGE_PATH = $StorageDir
$env:QDRANT__STORAGE__SNAPSHOTS_PATH = $SnapshotsDir
$env:QDRANT__SERVICE__HTTP_PORT = "6333"
$env:QDRANT__SERVICE__GRPC_PORT = "6334"
if (Test-Path $StaticDir) {
    $env:QDRANT__SERVICE__ENABLE_STATIC_CONTENT = "true"
    $env:QDRANT__SERVICE__STATIC_DIR = $StaticDir
}

Write-Host "[+] Starting Qdrant vector database on Windows: http://127.0.0.1:6333" -ForegroundColor Green
& $QdrantBin
