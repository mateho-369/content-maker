@echo off
setlocal
chcp 65001 >nul
title ComfyUI Video+SFX :8188
set "ENGINE_DIR=%~dp0"
if "%ENGINE_DIR:~-1%"=="\" set "ENGINE_DIR=%ENGINE_DIR:~0,-1%"
set "ROOT_DIR=%ENGINE_DIR%\.."
set "COMFY_DIR=%ROOT_DIR%\ComfyUI"
set "PORT=8188"
if not "%~1"=="" set "PORT=%~1"

if not exist "%COMFY_DIR%\main.py" (
  echo [ERROR] ComfyUI not found at %COMFY_DIR%
  echo         Clone: git clone https://github.com/comfyanonymous/ComfyUI "%COMFY_DIR%"
  pause
  exit /b 1
)

:: Find Comfy python
set "COMFY_PY="
if exist "%COMFY_DIR%\.venv\Scripts\python.exe" set "COMFY_PY=%COMFY_DIR%\.venv\Scripts\python.exe"
if not defined COMFY_PY if exist "%COMFY_DIR%\venv\Scripts\python.exe" set "COMFY_PY=%COMFY_DIR%\venv\Scripts\python.exe"
if not defined COMFY_PY if exist "%ENGINE_DIR%\.venv-studio\Scripts\python.exe" set "COMFY_PY=%ENGINE_DIR%\.venv-studio\Scripts\python.exe"

if not defined COMFY_PY (
  echo [ERROR] No python found for ComfyUI
  pause
  exit /b 1
)

echo [COMFYUI] Starting at %COMFY_DIR%
echo          Python: %COMFY_PY%
echo          Port  : %PORT%
echo          URL   : http://127.0.0.1:%PORT%/
echo.
:: Optional: --lowvram for 8GB cards if OOM
:: Add --lowvram flag if needed:
set "EXTRA_ARGS="
:: Uncomment next line if you get CUDA OOM on RTX 5070 8GB:
:: set "EXTRA_ARGS=--lowvram"

"%COMFY_PY%" "%COMFY_DIR%\main.py" --listen 127.0.0.1 --port %PORT% %EXTRA_ARGS%
pause
