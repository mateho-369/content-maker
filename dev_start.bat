@echo off
setlocal
chcp 65001 >nul
title Auto-Clip Dev - Frontend + Backend
set "ENGINE_DIR=%~dp0"
if "%ENGINE_DIR:~-1%"=="\" set "ENGINE_DIR=%ENGINE_DIR:~0,-1%"

set "STUDIO_PY="
if exist "%ENGINE_DIR%\.venv-studio\Scripts\python.exe" set "STUDIO_PY=%ENGINE_DIR%\.venv-studio\Scripts\python.exe"
if not defined STUDIO_PY if exist "%ENGINE_DIR%\.venv\Scripts\python.exe" set "STUDIO_PY=%ENGINE_DIR%\.venv\Scripts\python.exe"

echo [DEV] Starting backend :8000 and frontend :5173
echo      Backend : http://localhost:8000/
echo      Frontend dev: http://localhost:5173/ (proxies /api to :8000)

:: Backend
start "Backend :8000" cmd /k ""%STUDIO_PY%" -m ai_studio --port 8000 --host 0.0.0.0"

:: Frontend
pushd "%ENGINE_DIR%\ai_studio\frontend"
where npm >nul 2>&1
if %ERRORLEVEL%==0 (
  start "Frontend :5173" cmd /k "npm run dev"
) else (
  echo [ERROR] npm not found - install Node.js
)
popd

timeout /t 4 /nobreak >nul
start http://localhost:5173/
pause
