@echo off
setlocal
chcp 65001 >nul
title Auto-Clip Engine v3 Legacy :8001
set "ENGINE_DIR=%~dp0"
if "%ENGINE_DIR:~-1%"=="\" set "ENGINE_DIR=%ENGINE_DIR:~0,-1%"
set "PORT=8001"
if not "%~1"=="" set "PORT=%~1"

set "PY="
if exist "%ENGINE_DIR%\.venv-studio\Scripts\python.exe" set "PY=%ENGINE_DIR%\.venv-studio\Scripts\python.exe"
if not defined PY if exist "%ENGINE_DIR%\venv\Scripts\python.exe" set "PY=%ENGINE_DIR%\venv\Scripts\python.exe"

if not defined PY (
  echo [ERROR] No venv found
  pause
  exit /b 1
)

echo [LEGACY] Auto-Clip Engine v3 (src/) on :%PORT%
echo         URL: http://localhost:%PORT%/
"%PY%" -m uvicorn src.app:app --host 0.0.0.0 --port %PORT% --reload
pause
