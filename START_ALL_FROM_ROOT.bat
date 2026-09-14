@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Auto-Clip ROOT Launcher - All Projects

:: ============================================================
::  AUTO-CLIP - ROOT LAUNCHER
::  Place this file in: C:\Users\Makara\Desktop\auto-clip\START_ALL.bat
::  (This copy lives in Auto-Clip-Engine/START_ALL_FROM_ROOT.bat for reference)
::  Copy it one level up to auto-clip\ and double-click.
::
::  It launches:
::    - Ollama :11434
::    - ComfyUI :8188
::    - RVC WebUI :9513 / :7865
::    - Khmer Studio :8000
:: ============================================================

:: Determine where we are
set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

:: Support both placements: if this bat is inside Auto-Clip-Engine, go up one
if exist "%ROOT_DIR%\ai_studio\app.py" (
  :: We are inside Auto-Clip-Engine itself
  set "ENGINE_DIR=%ROOT_DIR%"
  set "ROOT_DIR=%ENGINE_DIR%\.."
) else (
  :: We are in the parent auto-clip folder
  set "ENGINE_DIR=%ROOT_DIR%\Auto-Clip-Engine"
)

set "COMFY_DIR=%ROOT_DIR%\ComfyUI"
set "RVC_DIR=%ROOT_DIR%\Retrieval-based-Voice-Conversion-WebUI"

echo.
echo  ======================================================
echo    AUTO-CLIP ROOT - MASTER LAUNCHER
echo  ======================================================
echo    Root   : %ROOT_DIR%
echo    Engine : %ENGINE_DIR%
echo    ComfyUI: %COMFY_DIR%
echo    RVC    : %RVC_DIR%
echo  ======================================================
echo.

:: Delegate to Engine's START.bat if it exists
if exist "%ENGINE_DIR%\START.bat" (
  echo [INFO] Delegating to %ENGINE_DIR%\START.bat ...
  call "%ENGINE_DIR%\START.bat" %*
  exit /b %ERRORLEVEL%
)

:: Fallback inline launch if START.bat not found (should not happen)
echo [WARN] %ENGINE_DIR%\START.bat not found - running inline fallback...

:: Python detection
set "PY_CMD="
where py >nul 2>&1 && set "PY_CMD=py"
if "%PY_CMD%"=="" where python >nul 2>&1 && set "PY_CMD=python"
if "%PY_CMD%"=="" (
  echo [ERROR] Python not found
  pause
  exit /b 1
)

:: Studio venv
set "STUDIO_PY="
if exist "%ENGINE_DIR%\.venv-studio\Scripts\python.exe" set "STUDIO_PY=%ENGINE_DIR%\.venv-studio\Scripts\python.exe"
if not defined STUDIO_PY if exist "%ENGINE_DIR%\venv\Scripts\python.exe" set "STUDIO_PY=%ENGINE_DIR%\venv\Scripts\python.exe"
if not defined STUDIO_PY set "STUDIO_PY=%PY_CMD%"

:: Ollama
where ollama >nul 2>&1
if %ERRORLEVEL%==0 (
  powershell -NoProfile -Command "try { Invoke-WebRequest -Uri http://127.0.0.1:11434/api/tags -TimeoutSec 2 -UseBasicParsing | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
  if !ERRORLEVEL! NEQ 0 (
    start "Ollama :11434" cmd /k "ollama serve"
    timeout /t 3 /nobreak >nul
  )
)

:: ComfyUI
if exist "%COMFY_DIR%\main.py" (
  powershell -NoProfile -Command "try { Invoke-WebRequest -Uri http://127.0.0.1:8188/system_stats -TimeoutSec 2 -UseBasicParsing | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
  if !ERRORLEVEL! NEQ 0 (
    if exist "%COMFY_DIR%\.venv\Scripts\python.exe" (
      start "ComfyUI :8188" cmd /k ""%COMFY_DIR%\.venv\Scripts\python.exe" "%COMFY_DIR%\main.py" --listen 127.0.0.1 --port 8188"
    ) else (
      start "ComfyUI :8188" cmd /k ""%STUDIO_PY%" "%COMFY_DIR%\main.py" --listen 127.0.0.1 --port 8188"
    )
    timeout /t 5 /nobreak >nul
  )
)

:: RVC
if exist "%RVC_DIR%" (
  if exist "%RVC_DIR%\api.py" (
    start "RVC API :9513" cmd /k ""%STUDIO_PY%" "%RVC_DIR%\api.py" --port 9513"
  ) else if exist "%RVC_DIR%\infer-web.py" (
    start "RVC WebUI :7865" cmd /k ""%STUDIO_PY%" "%RVC_DIR%\infer-web.py" --p 7865"
  )
  timeout /t 3 /nobreak >nul
)

:: Studio
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri http://127.0.0.1:8000/api/health -TimeoutSec 2 -UseBasicParsing | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if !ERRORLEVEL!==0 (
  start http://localhost:8000/
) else (
  start "Khmer Studio :8000" cmd /k ""%STUDIO_PY%" -m ai_studio --port 8000 --host 0.0.0.0"
  timeout /t 6 /nobreak >nul
  start http://localhost:8000/
)

echo All launched - http://localhost:8000/
pause
