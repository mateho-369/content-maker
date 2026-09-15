@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Auto-Clip - Full Setup

:: ============================================================
::  Auto-Clip Engine - FULL FIRST-TIME SETUP
::  Run this once after cloning, or when you want to reinstall.
::  It sets up:
::    - Studio venv + deps + frontend
::    - ComfyUI venv + deps + MMAudio custom node
::    - RVC WebUI venv + deps
::    - Ollama models
::    - Optional Khmer TTS
:: ============================================================

set "ENGINE_DIR=%~dp0"
if "%ENGINE_DIR:~-1%"=="\" set "ENGINE_DIR=%ENGINE_DIR:~0,-1%"
set "ROOT_DIR=%ENGINE_DIR%\.."
set "COMFY_DIR=%ROOT_DIR%\ComfyUI"
set "RVC_DIR=%ROOT_DIR%\Retrieval-based-Voice-Conversion-WebUI"

echo.
echo  ======================================================
echo    AUTO-CLIP - FULL SETUP
echo  ======================================================
echo    Engine : %ENGINE_DIR%
echo    Root   : %ROOT_DIR%
echo  ======================================================
echo.

:: Python detection
set "PY_CMD="
where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3.11 --version >nul 2>&1
  if !ERRORLEVEL!==0 (set "PY_CMD=py -3.11") else (set "PY_CMD=py")
)
if "%PY_CMD%"=="" (
  where python >nul 2>&1
  if %ERRORLEVEL%==0 set "PY_CMD=python"
)
if "%PY_CMD%"=="" (
  echo [ERROR] Python not found. Install Python 3.11: https://python.org
  pause
  exit /b 1
)
echo [OK] Python: %PY_CMD%
%PY_CMD% --version
echo.

:: ----------------------------------------------------------
:: 1. Studio Setup
:: ----------------------------------------------------------
echo --------------- 1/5 Studio ---------------
set "STUDIO_VENV=%ENGINE_DIR%\.venv-studio"
if not exist "%STUDIO_VENV%\Scripts\python.exe" (
  echo [SETUP] Creating %STUDIO_VENV% ...
  %PY_CMD% -m venv "%STUDIO_VENV%"
) else (
  echo [OK] Reusing existing %STUDIO_VENV%
)
set "STUDIO_PY=%STUDIO_VENV%\Scripts\python.exe"
echo [INFO] Using %STUDIO_PY%

echo [SETUP] Upgrading pip...
"%STUDIO_PY%" -m pip install --upgrade pip setuptools wheel

echo [SETUP] Installing requirements-studio.txt ...
"%STUDIO_PY%" -m pip install -r "%ENGINE_DIR%\requirements-studio.txt"
if %ERRORLEVEL% NEQ 0 echo [WARN] Studio deps failed - check network

:: Also install legacy requirements if you want ai_creator + auto-clip v3
choice /M "Install legacy ai_creator + auto-clip v3 deps too (moviepy, faster-whisper etc)?"
if %ERRORLEVEL%==1 (
  "%STUDIO_PY%" -m pip install -r "%ENGINE_DIR%\requirements.txt"
)

:: Frontend build
where npm >nul 2>&1
if %ERRORLEVEL%==0 (
  if exist "%ENGINE_DIR%\ai_studio\frontend\package.json" (
    echo [SETUP] Building frontend (React/Vite)...
    pushd "%ENGINE_DIR%\ai_studio\frontend"
    call npm ci
    call npm run build
    popd
    echo [OK] Frontend built to ai_studio/static/
  )
) else (
  echo [WARN] npm not found - skipping frontend build. Install Node.js 18+ to build UI.
  echo        The backend will still serve the last built static files if present.
)

:: Create data folders via --check
echo [SETUP] Creating data folders...
"%STUDIO_PY%" -m ai_studio --check
echo.

:: ----------------------------------------------------------
:: 2. ComfyUI Setup
:: ----------------------------------------------------------
echo --------------- 2/5 ComfyUI ---------------
if exist "%COMFY_DIR%\main.py" (
  echo [OK] Found ComfyUI at %COMFY_DIR%
  set "COMFY_VENV=%COMFY_DIR%\.venv"
  if not exist "%COMFY_VENV%\Scripts\python.exe" (
    echo [SETUP] Creating ComfyUI venv at %COMFY_VENV% ...
    %PY_CMD% -m venv "%COMFY_VENV%"
  )
  set "COMFY_PY=%COMFY_VENV%\Scripts\python.exe"
  echo [SETUP] Installing ComfyUI requirements...
  "%COMFY_PY%" -m pip install --upgrade pip
  "%COMFY_PY%" -m pip install -r "%COMFY_DIR%\requirements.txt"
  :: Torch CUDA - ensure CUDA build
  echo [INFO] Checking torch CUDA...
  "%COMFY_PY%" -c "import torch; print(torch.__version__, 'cuda:', torch.cuda.is_available())" 2>nul
  if !ERRORLEVEL! NEQ 0 (
    echo [SETUP] Installing torch CUDA 12.8...
    "%COMFY_PY%" -m pip install torch==2.7.1+cu128 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
  )

  :: Custom node MMAudio
  if not exist "%COMFY_DIR%\custom_nodes\ComfyUI-MMAudio" (
    echo [SETUP] Cloning ComfyUI-MMAudio custom node...
    where git >nul 2>&1
    if !ERRORLEVEL!==0 (
      git clone https://github.com/kijai/ComfyUI-MMAudio "%COMFY_DIR%\custom_nodes\ComfyUI-MMAudio"
    ) else (
      echo [WARN] git not found - manually clone ComfyUI-MMAudio into custom_nodes/
    )
  ) else (
    echo [OK] ComfyUI-MMAudio already present
  )

  echo [INFO] ComfyUI models need manual placement - see README-STUDIO.md
  echo        Expected:
  echo          ComfyUI/models/diffusion_models/wan2.1_t2v_1.3b_bf16.safetensors
  echo          ComfyUI/models/vae/wan_2.1_vae.safetensors
  echo          ComfyUI/models/clip/umt5_xxl_fp8_e4m3fn_scaled.safetensors
  echo          ComfyUI/models/mmaudio/mmaudio_small_08_44k_v2.safetensors
) else (
  echo [SKIP] ComfyUI not found at %COMFY_DIR%
  echo        To install:
  echo          cd /d "%ROOT_DIR%"
  echo          git clone https://github.com/comfyanonymous/ComfyUI
  echo          Then re-run this setup.
)
echo.

:: ----------------------------------------------------------
:: 3. RVC WebUI Setup
:: ----------------------------------------------------------
echo --------------- 3/5 RVC WebUI ---------------
if exist "%RVC_DIR%" (
  echo [OK] Found RVC at %RVC_DIR%
  :: Detect venv
  set "RVC_VENV="
  if exist "%RVC_DIR%\.venv\Scripts\python.exe" set "RVC_VENV=%RVC_DIR%\.venv"
  if not defined RVC_VENV if exist "%RVC_DIR%\venv\Scripts\python.exe" set "RVC_VENV=%RVC_DIR%\venv"
  if not defined RVC_VENV (
    echo [SETUP] Creating RVC venv at %RVC_DIR%\.venv ...
    %PY_CMD% -m venv "%RVC_DIR%\.venv"
    set "RVC_VENV=%RVC_DIR%\.venv"
  )
  set "RVC_PY=%RVC_VENV%\Scripts\python.exe"
  echo [INFO] Using %RVC_PY%

  if exist "%RVC_DIR%\requirements.txt" (
    echo [SETUP] Installing RVC requirements...
    "%RVC_PY%" -m pip install --upgrade pip
    "%RVC_PY%" -m pip install -r "%RVC_DIR%\requirements.txt"
  )
  if exist "%RVC_DIR%\requirements-win.txt" (
    "%RVC_PY%" -m pip install -r "%RVC_DIR%\requirements-win.txt"
  )
  echo [OK] RVC setup done. Train voices via Studio UI -> Voices.
) else (
  echo [SKIP] RVC not found at %RVC_DIR%
  echo        To install:
  echo          cd /d "%ROOT_DIR%"
  echo          git clone https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI
)
echo.

:: ----------------------------------------------------------
:: 4. Ollama
:: ----------------------------------------------------------
echo --------------- 4/5 Ollama ---------------
where ollama >nul 2>&1
if %ERRORLEVEL%==0 (
  echo [OK] Ollama installed
  echo [SETUP] Pulling models (this may take a while, 2-5GB each)...
  echo        - sailor2:8b (Khmer-capable, recommended)
  ollama pull sailor2:8b
  echo        - llama3.2:3b (CPU fallback)
  ollama pull llama3.2:3b
  ollama list
) else (
  echo [WARN] Ollama not installed
  echo        Install: winget install Ollama.Ollama
  echo        Then: ollama pull sailor2:8b && ollama pull llama3.2:3b
)
echo.

:: ----------------------------------------------------------
:: 5. Khmer TTS (optional)
:: ----------------------------------------------------------
echo --------------- 5/5 Khmer TTS ---------------
choice /M "Setup Khmer TTS (sherpa-onnx + MMS khm) - needs ~10min + internet"
if %ERRORLEVEL%==1 (
  echo [SETUP] Running Khmer TTS setup...
  if exist "%ENGINE_DIR%\scripts\setup_khmer_tts.ps1" (
    powershell -ExecutionPolicy Bypass -File "%ENGINE_DIR%\scripts\setup_khmer_tts.ps1"
  ) else if exist "%ENGINE_DIR%\scripts\setup_khmer_tts.sh" (
    :: Try bash if available (Git Bash)
    where bash >nul 2>&1
    if !ERRORLEVEL!==0 (
      bash "%ENGINE_DIR%/scripts/setup_khmer_tts.sh"
    ) else (
      echo [WARN] Need bash or run setup_khmer_tts.ps1 manually
    )
  )
  :: Also pip install sherpa-onnx in studio venv
  "%STUDIO_PY%" -m pip install sherpa-onnx
) else (
  echo [SKIP] Khmer TTS - will use placeholder voice until installed
  echo        Run later: scripts\setup_khmer_tts.ps1
)
echo.

:: ----------------------------------------------------------
:: Final check
:: ----------------------------------------------------------
echo  ======================================================
echo    SETUP COMPLETE - Final Readiness Report
echo  ======================================================
"%STUDIO_PY%" -m ai_studio --check

echo.
echo  Next: Run START.bat to launch all services
echo.
pause
