@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Auto-Clip Master Launcher

:: ============================================================
::  Auto-Clip Engine - ONE CLICK MASTER LAUNCHER
::  Place: C:\Users\Makara\Desktop\auto-clip\Auto-Clip-Engine\START.bat
::  It auto-detects sibling folders:
::    ..\ComfyUI
::    ..\Retrieval-based-Voice-Conversion-WebUI
::  And launches 4 services in separate windows:
::    1. Ollama        :11434
::    2. ComfyUI       :8188  (Wan video + MMAudio SFX)
::    3. RVC WebUI     :9513  (voice timbre API) / :7865 (gradio)
::    4. Khmer Studio  :8000
:: ============================================================

set "ENGINE_DIR=%~dp0"
:: Remove trailing backslash for clean join
if "%ENGINE_DIR:~-1%"=="\" set "ENGINE_DIR=%ENGINE_DIR:~0,-1%"
set "ROOT_DIR=%ENGINE_DIR%\.."
set "COMFY_DIR=%ROOT_DIR%\ComfyUI"
set "RVC_DIR=%ROOT_DIR%\Retrieval-based-Voice-Conversion-WebUI"
set "STUDIO_PORT=8000"
set "COMFY_PORT=8188"
set "RVC_PORT=9513"
set "OLLAMA_PORT=11434"

:: Allow override via args: --studio-only, --no-comfy, --no-rvc, --no-ollama
set "SKIP_COMFY=0"
set "SKIP_RVC=0"
set "SKIP_OLLAMA=0"
set "STUDIO_ONLY=0"
for %%A in (%*) do (
  if /I "%%A"=="--no-comfy" set "SKIP_COMFY=1"
  if /I "%%A"=="--no-rvc" set "SKIP_RVC=1"
  if /I "%%A"=="--no-ollama" set "SKIP_OLLAMA=1"
  if /I "%%A"=="--studio-only" set "STUDIO_ONLY=1"
)
if "%STUDIO_ONLY%"=="1" (
  set "SKIP_COMFY=1"
  set "SKIP_RVC=1"
  set "SKIP_OLLAMA=1"
)

echo.
echo  ======================================================
echo    AUTO-CLIP ENGINE - MASTER LAUNCHER
echo  ======================================================
echo    Engine : %ENGINE_DIR%
echo    Root   : %ROOT_DIR%
echo    ComfyUI: %COMFY_DIR%
echo    RVC    : %RVC_DIR%
echo    Ports  : Studio=%STUDIO_PORT% Comfy=%COMFY_PORT% RVC=%RVC_PORT% Ollama=%OLLAMA_PORT%
echo  ======================================================
echo.

:: ----------------------------------------------------------
:: 1. Detect Python
:: ----------------------------------------------------------
set "PY_CMD="
where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3.11 --version >nul 2>&1
  if !ERRORLEVEL!==0 (
    set "PY_CMD=py -3.11"
  ) else (
    py --version >nul 2>&1
    if !ERRORLEVEL!==0 set "PY_CMD=py"
  )
)
if "%PY_CMD%"=="" (
  where python >nul 2>&1
  if %ERRORLEVEL%==0 set "PY_CMD=python"
)
if "%PY_CMD%"=="" (
  echo [ERROR] Python not found! Install Python 3.11 from https://python.org
  echo         Make sure to tick "Add to PATH"
  pause
  exit /b 1
)
echo [OK] Python: %PY_CMD%
%PY_CMD% --version

:: ----------------------------------------------------------
:: 2. Studio venv check
:: ----------------------------------------------------------
set "STUDIO_PY="
if exist "%ENGINE_DIR%\.venv-studio\Scripts\python.exe" set "STUDIO_PY=%ENGINE_DIR%\.venv-studio\Scripts\python.exe"
if not defined STUDIO_PY if exist "%ENGINE_DIR%\.venv\Scripts\python.exe" set "STUDIO_PY=%ENGINE_DIR%\.venv\Scripts\python.exe"
if not defined STUDIO_PY if exist "%ENGINE_DIR%\venv\Scripts\python.exe" set "STUDIO_PY=%ENGINE_DIR%\venv\Scripts\python.exe"

if not defined STUDIO_PY (
  echo.
  echo [SETUP] Studio venv not found - creating .venv-studio ...
  %PY_CMD% -m venv "%ENGINE_DIR%\.venv-studio"
  if !ERRORLEVEL! NEQ 0 (
    echo [ERROR] Failed to create venv
    pause
    exit /b 1
  )
  set "STUDIO_PY=%ENGINE_DIR%\.venv-studio\Scripts\python.exe"
  echo [SETUP] Installing studio requirements...
  "%STUDIO_PY%" -m pip install --upgrade pip setuptools wheel
  "%STUDIO_PY%" -m pip install -r "%ENGINE_DIR%\requirements-studio.txt"
  if !ERRORLEVEL! NEQ 0 (
    echo [WARN] pip install failed - check network
  )
  :: Optional frontend build
  where npm >nul 2>&1
  if !ERRORLEVEL!==0 (
    if exist "%ENGINE_DIR%\ai_studio\frontend\package.json" (
      echo [SETUP] Building frontend...
      pushd "%ENGINE_DIR%\ai_studio\frontend"
      call npm ci
      call npm run build
      popd
    )
  )
) else (
  echo [OK] Studio venv: %STUDIO_PY%
)

:: ----------------------------------------------------------
:: 3. ffmpeg check
:: ----------------------------------------------------------
where ffmpeg >nul 2>&1
if %ERRORLEVEL%==0 (
  echo [OK] ffmpeg found
) else (
  echo [WARN] ffmpeg not on PATH - will try bundled imageio-ffmpeg
  echo        For best results: winget install Gyan.FFmpeg
)

:: ----------------------------------------------------------
:: 4. Ollama check & start
:: ----------------------------------------------------------
if "%SKIP_OLLAMA%"=="0" (
  where ollama >nul 2>&1
  if %ERRORLEVEL%==0 (
    echo [OK] Ollama installed
    :: Check if running
    powershell -NoProfile -Command "try { Invoke-WebRequest -Uri http://127.0.0.1:%OLLAMA_PORT%/api/tags -TimeoutSec 2 -UseBasicParsing | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
    if !ERRORLEVEL! NEQ 0 (
      echo [INFO] Ollama not running - starting in new window...
      start "Ollama :%OLLAMA_PORT%" cmd /k "ollama serve"
      echo [WAIT] Waiting 3s for Ollama...
      timeout /t 3 /nobreak >nul
    ) else (
      echo [OK] Ollama already running on :%OLLAMA_PORT%
    )
    :: Check models
    echo [INFO] Checking Ollama models (sailor2:8b, llama3.2:3b)...
    ollama list | findstr /i "sailor2" >nul
    if !ERRORLEVEL! NEQ 0 (
      echo [WARN] sailor2:8b not found - pulling in background window...
      start "Ollama Pull sailor2:8b" cmd /k "ollama pull sailor2:8b"
    )
    ollama list | findstr /i "llama3.2" >nul
    if !ERRORLEVEL! NEQ 0 (
      echo [WARN] llama3.2:3b not found - pulling in background window...
      start "Ollama Pull llama3.2:3b" cmd /k "ollama pull llama3.2:3b"
    )
  ) else (
    echo [WARN] Ollama not installed - Studio will use deterministic fallbacks
    echo        Install: winget install Ollama.Ollama
  )
) else (
  echo [SKIP] Ollama
)

:: ----------------------------------------------------------
:: 5. ComfyUI start
:: ----------------------------------------------------------
if "%SKIP_COMFY%"=="0" (
  if exist "%COMFY_DIR%\main.py" (
    echo [OK] ComfyUI found at %COMFY_DIR%
    :: Detect Comfy venv
    set "COMFY_PY="
    if exist "%COMFY_DIR%\.venv\Scripts\python.exe" set "COMFY_PY=%COMFY_DIR%\.venv\Scripts\python.exe"
    if not defined COMFY_PY if exist "%COMFY_DIR%\venv\Scripts\python.exe" set "COMFY_PY=%COMFY_DIR%\venv\Scripts\python.exe"
    if not defined COMFY_PY if exist "%COMFY_DIR%\.venv-studio\Scripts\python.exe" set "COMFY_PY=%COMFY_DIR%\.venv-studio\Scripts\python.exe"
    if not defined COMFY_PY set "COMFY_PY=%STUDIO_PY%"

    :: Check if already running
    powershell -NoProfile -Command "try { Invoke-WebRequest -Uri http://127.0.0.1:%COMFY_PORT%/system_stats -TimeoutSec 2 -UseBasicParsing | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
    if !ERRORLEVEL!==0 (
      echo [OK] ComfyUI already running on :%COMFY_PORT%
    ) else (
      echo [START] Launching ComfyUI on :%COMFY_PORT% ...
      start "ComfyUI Video+SFX :%COMFY_PORT%" cmd /k ""%COMFY_PY%" "%COMFY_DIR%\main.py" --listen 127.0.0.1 --port %COMFY_PORT%"
      echo [WAIT] Waiting 5s for ComfyUI to init...
      timeout /t 5 /nobreak >nul
    )
  ) else (
    echo [WARN] ComfyUI not found at %COMFY_DIR% - video/SFX will use previz fallback
    echo        Clone: git clone https://github.com/comfyanonymous/ComfyUI "%COMFY_DIR%"
  )
) else (
  echo [SKIP] ComfyUI
)

:: ----------------------------------------------------------
:: 6. RVC WebUI start
:: ----------------------------------------------------------
if "%SKIP_RVC%"=="0" (
  if exist "%RVC_DIR%" (
    echo [OK] RVC folder found at %RVC_DIR%
    set "RVC_PY="
    if exist "%RVC_DIR%\.venv\Scripts\python.exe" set "RVC_PY=%RVC_DIR%\.venv\Scripts\python.exe"
    if not defined RVC_PY if exist "%RVC_DIR%\venv\Scripts\python.exe" set "RVC_PY=%RVC_DIR%\venv\Scripts\python.exe"
    if not defined RVC_PY if exist "%RVC_DIR%\runtime\python.exe" set "RVC_PY=%RVC_DIR%\runtime\python.exe"
    if not defined RVC_PY set "RVC_PY=%STUDIO_PY%"

    :: Check if API already running
    powershell -NoProfile -Command "try { Invoke-WebRequest -Uri http://127.0.0.1:%RVC_PORT%/ -TimeoutSec 2 -UseBasicParsing | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
    if !ERRORLEVEL!==0 (
      echo [OK] RVC API already running on :%RVC_PORT%
    ) else (
      echo [START] Launching RVC WebUI...
      :: Try to detect best entry point
      if exist "%RVC_DIR%\api.py" (
        echo [INFO] Using api.py --port %RVC_PORT%
        start "RVC API :%RVC_PORT%" cmd /k ""%RVC_PY%" "%RVC_DIR%\api.py" --port %RVC_PORT%"
      ) else if exist "%RVC_DIR%\infer-web.py" (
        echo [INFO] Using infer-web.py (Gradio :7865 + API :%RVC_PORT% attempt)
        start "RVC WebUI :7865" cmd /k ""%RVC_PY%" "%RVC_DIR%\infer-web.py" --p 7865 --api_port %RVC_PORT%"
      ) else if exist "%RVC_DIR%\webui.py" (
        echo [INFO] Using webui.py
        start "RVC WebUI" cmd /k ""%RVC_PY%" "%RVC_DIR%\webui.py" --port 7865"
      ) else if exist "%RVC_DIR%\tools\infer_api.py" (
        start "RVC API :%RVC_PORT%" cmd /k ""%RVC_PY%" "%RVC_DIR%\tools\infer_api.py" --port %RVC_PORT%"
      ) else (
        echo [WARN] Could not detect RVC entry point. Tried api.py, infer-web.py, webui.py
        echo        Start it manually: cd /d "%RVC_DIR%" ^&^& python infer-web.py
      )
      timeout /t 3 /nobreak >nul
    )
  ) else (
    echo [WARN] RVC not found at %RVC_DIR% - voice timbre will bypass (base Khmer voice used)
    echo        Clone: git clone https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI "%RVC_DIR%"
  )
) else (
  echo [SKIP] RVC
)

:: ----------------------------------------------------------
:: 7. Studio readiness check
:: ----------------------------------------------------------
echo.
echo [CHECK] Running studio readiness probe...
"%STUDIO_PY%" -m ai_studio --check
echo.

:: ----------------------------------------------------------
:: 8. Start Studio (main app)
:: ----------------------------------------------------------
:: Check if already running
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri http://127.0.0.1:%STUDIO_PORT%/api/health -TimeoutSec 2 -UseBasicParsing | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if !ERRORLEVEL!==0 (
  echo [OK] Studio already running on :%STUDIO_PORT% - opening browser...
  start http://localhost:%STUDIO_PORT%/
) else (
  echo [START] Launching Khmer AI Content Studio on :%STUDIO_PORT% ...
  echo         URL: http://localhost:%STUDIO_PORT%/
  :: Launch in new window, keep open
  start "Khmer Studio :%STUDIO_PORT%" cmd /k ""%STUDIO_PY%" -m ai_studio --port %STUDIO_PORT% --host 0.0.0.0"
  echo [WAIT] Waiting 6s for studio to boot...
  timeout /t 6 /nobreak >nul
  echo [OPEN] Opening browser at http://localhost:%STUDIO_PORT%/
  start http://localhost:%STUDIO_PORT%/
)

echo.
echo  ======================================================
echo    ALL SERVICES LAUNCHED
echo  ======================================================
echo    Studio  : http://localhost:%STUDIO_PORT%/   (main UI)
echo    ComfyUI : http://127.0.0.1:%COMFY_PORT%/    (video + SFX)
echo    Ollama  : http://127.0.0.1:%OLLAMA_PORT%/   (LLM)
echo    RVC API : http://127.0.0.1:%RVC_PORT%/  or http://127.0.0.1:7865/ (Gradio)
echo.
echo    To check status: run check_system.bat
echo    To stop all   : run STOP_ALL.bat
echo    Logs are in each service window.
echo  ======================================================
echo.
echo Press any key to run a final health check...
pause >nul
"%STUDIO_PY%" -m ai_studio --check
echo.
pause
