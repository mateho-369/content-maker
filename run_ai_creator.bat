@echo off
setlocal
chcp 65001 >nul
title AI Content Creator :8002
set "ENGINE_DIR=%~dp0"
if "%ENGINE_DIR:~-1%"=="\" set "ENGINE_DIR=%ENGINE_DIR:~0,-1%"
set "PORT=8002"
if not "%~1"=="" set "PORT=%~1"

set "PY="
if exist "%ENGINE_DIR%\.venv-studio\Scripts\python.exe" set "PY=%ENGINE_DIR%\.venv-studio\Scripts\python.exe"
if not defined PY if exist "%ENGINE_DIR%\.venv\Scripts\python.exe" set "PY=%ENGINE_DIR%\.venv\Scripts\python.exe"
if not defined PY if exist "%ENGINE_DIR%\venv\Scripts\python.exe" set "PY=%ENGINE_DIR%\venv\Scripts\python.exe"

if not defined PY (
  echo [ERROR] No venv found. Run setup_all.bat
  pause
  exit /b 1
)

echo [AI_CREATOR] Starting on :%PORT%
echo             URL: http://localhost:%PORT%/
echo             Note: Khmer Studio uses :8000, so this uses :8002 to avoid conflict
"%PY%" -m uvicorn ai_creator.app:app --host 0.0.0.0 --port %PORT%
pause
