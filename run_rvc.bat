@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title RVC WebUI
set "ENGINE_DIR=%~dp0"
if "%ENGINE_DIR:~-1%"=="\" set "ENGINE_DIR=%ENGINE_DIR:~0,-1%"
set "ROOT_DIR=%ENGINE_DIR%\.."
set "RVC_DIR=%ROOT_DIR%\Retrieval-based-Voice-Conversion-WebUI"
set "API_PORT=9513"
set "WEB_PORT=7865"

if not exist "%RVC_DIR%" (
  echo [ERROR] RVC not found at %RVC_DIR%
  echo         Clone: git clone https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI "%RVC_DIR%"
  pause
  exit /b 1
)

:: Find RVC python
set "RVC_PY="
if exist "%RVC_DIR%\.venv\Scripts\python.exe" set "RVC_PY=%RVC_DIR%\.venv\Scripts\python.exe"
if not defined RVC_PY if exist "%RVC_DIR%\venv\Scripts\python.exe" set "RVC_PY=%RVC_DIR%\venv\Scripts\python.exe"
if not defined RVC_PY if exist "%RVC_DIR%\runtime\python.exe" set "RVC_PY=%RVC_DIR%\runtime\python.exe"
if not defined RVC_PY if exist "%ENGINE_DIR%\.venv-studio\Scripts\python.exe" set "RVC_PY=%ENGINE_DIR%\.venv-studio\Scripts\python.exe"

echo [RVC] Found at %RVC_DIR%
echo      Python: %RVC_PY%
echo.

:: Try different entry points - priority: api.py > infer-web.py > webui.py
if exist "%RVC_DIR%\api.py" (
  echo [START] Using api.py on port %API_PORT%
  echo        URL: http://127.0.0.1:%API_PORT%/
  "%RVC_PY%" "%RVC_DIR%\api.py" --port %API_PORT%
) else if exist "%RVC_DIR%\tools\infer_api.py" (
  echo [START] Using tools/infer_api.py on port %API_PORT%
  "%RVC_PY%" "%RVC_DIR%\tools\infer_api.py" --port %API_PORT%
) else if exist "%RVC_DIR%\infer-web.py" (
  echo [START] Using infer-web.py
  echo        Gradio: http://127.0.0.1:%WEB_PORT%/
  echo        Trying API on :%API_PORT% if supported...
  :: Some forks support --api_port, some don't
  "%RVC_PY%" "%RVC_DIR%\infer-web.py" --p %WEB_PORT% --api_port %API_PORT%
) else if exist "%RVC_DIR%\webui.py" (
  echo [START] Using webui.py on port %WEB_PORT%
  echo        Gradio: http://127.0.0.1:%WEB_PORT%/
  "%RVC_PY%" "%RVC_DIR%\webui.py" --port %WEB_PORT%
) else if exist "%RVC_DIR%\app.py" (
  echo [START] Using app.py
  "%RVC_PY%" "%RVC_DIR%\app.py"
) else (
  echo [ERROR] No known RVC entry point found.
  echo         Looked for: api.py, tools/infer_api.py, infer-web.py, webui.py, app.py
  echo         Check your RVC fork docs.
  dir /b "%RVC_DIR%\*.py"
  pause
  exit /b 1
)

pause
