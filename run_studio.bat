@echo off
setlocal
chcp 65001 >nul
title Khmer Studio :8000
set "ENGINE_DIR=%~dp0"
if "%ENGINE_DIR:~-1%"=="\" set "ENGINE_DIR=%ENGINE_DIR:~0,-1%"

set "PORT=8000"
if not "%~1"=="" set "PORT=%~1"

:: Find studio python
set "STUDIO_PY="
if exist "%ENGINE_DIR%\.venv-studio\Scripts\python.exe" set "STUDIO_PY=%ENGINE_DIR%\.venv-studio\Scripts\python.exe"
if not defined STUDIO_PY if exist "%ENGINE_DIR%\.venv\Scripts\python.exe" set "STUDIO_PY=%ENGINE_DIR%\.venv\Scripts\python.exe"
if not defined STUDIO_PY if exist "%ENGINE_DIR%\venv\Scripts\python.exe" set "STUDIO_PY=%ENGINE_DIR%\venv\Scripts\python.exe"

if not defined STUDIO_PY (
  echo [ERROR] No venv found. Run setup_all.bat first.
  pause
  exit /b 1
)

echo [STUDIO] Starting Khmer AI Content Studio on :%PORT%
echo         Using: %STUDIO_PY%
echo         URL  : http://localhost:%PORT%/
echo.
:: Check if frontend built
if not exist "%ENGINE_DIR%\ai_studio\static\assets" (
  echo [WARN] Frontend not built - UI may be empty. Run setup_all.bat or:
  echo        cd ai_studio\frontend ^&^& npm ci ^&^& npm run build
)

"%STUDIO_PY%" -m ai_studio --check
echo.
echo [START] Launching...
"%STUDIO_PY%" -m ai_studio --port %PORT% --host 0.0.0.0
pause
