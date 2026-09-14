<#
.SYNOPSIS
  PowerShell master launcher - more robust than .bat version
  Launches Ollama, ComfyUI, RVC, and Khmer Studio

.DESCRIPTION
  Place in Auto-Clip-Engine/ and run:
    powershell -ExecutionPolicy Bypass -File .\START.ps1
  Or from auto-clip root:
    powershell -ExecutionPolicy Bypass -File .\Auto-Clip-Engine\START.ps1

.PARAMETER StudioOnly
  Only start Studio, skip others

.PARAMETER NoComfy
  Skip ComfyUI

.PARAMETER NoRvc
  Skip RVC

.PARAMETER NoOllama
  Skip Ollama

.PARAMETER Port
  Studio port (default 8000)
#>
param(
  [switch]$StudioOnly,
  [switch]$NoComfy,
  [switch]$NoRvc,
  [switch]$NoOllama,
  [int]$Port = 8000,
  [int]$ComfyPort = 8188,
  [int]$RvcPort = 9513
)

$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$EngineDir = $PSScriptRoot
$RootDir = Split-Path $EngineDir -Parent
$ComfyDir = Join-Path $RootDir "ComfyUI"
$RvcDir = Join-Path $RootDir "Retrieval-based-Voice-Conversion-WebUI"

if ($StudioOnly) { $NoComfy = $true; $NoRvc = $true; $NoOllama = $true }

function Write-Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "[FAIL] $msg" -ForegroundColor Red }

function Test-Port($port) {
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $c.Connect("127.0.0.1", $port)
    $c.Close()
    return $true
  } catch { return $false }
}

function Find-StudioPython {
  $candidates = @(
    "$EngineDir\.venv-studio\Scripts\python.exe",
    "$EngineDir\.venv\Scripts\python.exe",
    "$EngineDir\venv\Scripts\python.exe"
  )
  foreach ($p in $candidates) { if (Test-Path $p) { return $p } }
  return "python"
}

$StudioPy = Find-StudioPython
Write-Info "Engine: $EngineDir"
Write-Info "Root: $RootDir"
Write-Info "Studio Python: $StudioPy"
Write-Info "Ports: Studio=$Port Comfy=$ComfyPort RVC=$RvcPort"

# 1. Ollama
if (-not $NoOllama) {
  if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-Ok "Ollama installed"
    if (-not (Test-Port 11434)) {
      Write-Info "Starting Ollama..."
      Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Normal
      Start-Sleep 3
    } else { Write-Ok "Ollama already running :11434" }
    $models = ollama list 2>$null
    if ($models -notmatch "sailor2") { Write-Warn "sailor2:8b missing - pulling in background"; Start-Process -FilePath "ollama" -ArgumentList "pull sailor2:8b" -WindowStyle Normal }
    if ($models -notmatch "llama3.2") { Write-Warn "llama3.2:3b missing - pulling in background"; Start-Process -FilePath "ollama" -ArgumentList "pull llama3.2:3b" -WindowStyle Normal }
  } else { Write-Warn "Ollama not installed - Studio will use fallbacks" }
} else { Write-Info "Skipping Ollama" }

# 2. ComfyUI
if (-not $NoComfy) {
  if (Test-Path "$ComfyDir\main.py") {
    if (-not (Test-Port $ComfyPort)) {
      $ComfyPy = $StudioPy
      if (Test-Path "$ComfyDir\.venv\Scripts\python.exe") { $ComfyPy = "$ComfyDir\.venv\Scripts\python.exe" }
      Write-Info "Starting ComfyUI on :$ComfyPort ..."
      Start-Process -FilePath $ComfyPy -ArgumentList "$ComfyDir\main.py --listen 127.0.0.1 --port $ComfyPort" -WorkingDirectory $ComfyDir -WindowStyle Normal
      Start-Sleep 5
    } else { Write-Ok "ComfyUI already running :$ComfyPort" }
  } else { Write-Warn "ComfyUI not found at $ComfyDir" }
} else { Write-Info "Skipping ComfyUI" }

# 3. RVC
if (-not $NoRvc) {
  if (Test-Path $RvcDir) {
    if (-not (Test-Port $RvcPort) -and -not (Test-Port 7865)) {
      $RvcPy = $StudioPy
      if (Test-Path "$RvcDir\.venv\Scripts\python.exe") { $RvcPy = "$RvcDir\.venv\Scripts\python.exe" }
      if (Test-Path "$RvcDir\api.py") {
        Write-Info "Starting RVC API :$RvcPort"
        Start-Process -FilePath $RvcPy -ArgumentList "$RvcDir\api.py --port $RvcPort" -WorkingDirectory $RvcDir -WindowStyle Normal
      } elseif (Test-Path "$RvcDir\infer-web.py") {
        Write-Info "Starting RVC WebUI :7865"
        Start-Process -FilePath $RvcPy -ArgumentList "$RvcDir\infer-web.py --p 7865" -WorkingDirectory $RvcDir -WindowStyle Normal
      }
      Start-Sleep 3
    } else { Write-Ok "RVC already running" }
  } else { Write-Warn "RVC not found at $RvcDir" }
} else { Write-Info "Skipping RVC" }

# 4. Readiness
Write-Info "Running readiness check..."
& $StudioPy -m ai_studio --check

# 5. Studio
if (-not (Test-Port $Port)) {
  Write-Info "Starting Khmer Studio on :$Port -> http://localhost:$Port/"
  Start-Process -FilePath $StudioPy -ArgumentList "-m ai_studio --port $Port --host 0.0.0.0" -WorkingDirectory $EngineDir -WindowStyle Normal
  Start-Sleep 6
} else { Write-Ok "Studio already running :$Port" }

Write-Info "Opening browser http://localhost:$Port/"
Start-Process "http://localhost:$Port/"

Write-Host ""
Write-Host "======================================================" -ForegroundColor Green
Write-Host "  ALL SERVICES LAUNCHED" -ForegroundColor Green
Write-Host "  Studio  : http://localhost:$Port/" -ForegroundColor White
Write-Host "  ComfyUI : http://127.0.0.1:$ComfyPort/" -ForegroundColor White
Write-Host "  Ollama  : http://127.0.0.1:11434/" -ForegroundColor White
Write-Host "  RVC     : http://127.0.0.1:$RvcPort/ or :7865" -ForegroundColor White
Write-Host "======================================================" -ForegroundColor Green
