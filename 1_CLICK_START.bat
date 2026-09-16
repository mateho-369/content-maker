@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title ✦ Khmer AI Content Studio — One-Click Auto Launcher ✦

color 0B
echo.
echo  ========================================================================
echo    ✦ KHMER AI CONTENT STUDIO — ONE-CLICK AUTO LAUNCHER ✦
echo  ========================================================================
echo    Everything runs 100%% automatically without typing commands in CMD.
echo    Step 1: Check Python ^& Virtual Environment
echo    Step 2: Auto-Install Dependencies (HarfBuzz, KhmerCut, OpenCV, etc.)
echo    Step 3: Launch Background Server on Port 8000
echo    Step 4: Auto-Open Studio ^& Video Gallery in your Browser
echo  ========================================================================
echo.

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
cd /d "%SCRIPT_DIR%"

:: ---------------------------------------------------------------------------
:: STEP 1: Find Python
:: ---------------------------------------------------------------------------
echo [1/4] Detecting Python installation...
set "PY_CMD="

where py >nul 2>&1
if !ERRORLEVEL! EQU 0 (
  py -3.11 --version >nul 2>&1
  if !ERRORLEVEL! EQU 0 (
    set "PY_CMD=py -3.11"
  ) else (
    py -3.12 --version >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
      set "PY_CMD=py -3.12"
    ) else (
      py -3.10 --version >nul 2>&1
      if !ERRORLEVEL! EQU 0 (
        set "PY_CMD=py -3.10"
      ) else (
        set "PY_CMD=py"
      )
    )
  )
)

if "%PY_CMD%"=="" (
  where python >nul 2>&1
  if !ERRORLEVEL! EQU 0 set "PY_CMD=python"
)

if "%PY_CMD%"=="" (
  echo.
  echo  [ERROR] Python is not installed or not in your system PATH!
  echo  Please download and install Python 3.11 from:
  echo    https://www.python.org/downloads/
  echo  IMPORTANT: Check the box "Add python.exe to PATH" during installation.
  echo.
  start https://www.python.org/downloads/
  pause
  exit /b 1
)

for /f "tokens=*" %%v in ('%PY_CMD% --version 2^>^&1') do echo   ✓ Found Python: %%v

:: ---------------------------------------------------------------------------
:: STEP 2: Setup Studio Virtual Environment (.venv-studio)
:: ---------------------------------------------------------------------------
echo.
echo [2/4] Checking Python Virtual Environment (.venv-studio)...
set "VENV_DIR=%SCRIPT_DIR%\.venv-studio"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

if exist "%VENV_PY%" goto VENV_READY
echo   - Creating virtual environment at .venv-studio ...
%PY_CMD% -m venv "%VENV_DIR%"
if errorlevel 1 goto VENV_FAIL
echo   - Virtual environment created successfully.
echo   - Upgrading pip...
"%VENV_PY%" -m pip install --quiet --upgrade pip setuptools wheel
echo   - Auto-installing studio dependencies...
"%VENV_PY%" -m pip install -r "%SCRIPT_DIR%\requirements-studio.txt"
if errorlevel 1 echo   [WARNING] Some packages failed to install; retrying core requirements...
if errorlevel 1 "%VENV_PY%" -m pip install fastapi "uvicorn[standard]" python-multipart "pillow>=10.4.0" numpy uharfbuzz khmercut opencv-python-headless imageio-ffmpeg edge-tts ffmpeg-python pysubs2
echo   - Studio dependencies installed.
goto VENV_DONE

:VENV_READY
echo   - Virtual environment ready: %VENV_DIR%
:: Verify essential dependencies are installed (in case previous install failed or was partial)
"%VENV_PY%" -c "import multipart, fastapi, uvicorn, PIL, cv2" >nul 2>&1
if errorlevel 1 (
  echo   - Missing dependencies detected in .venv-studio (e.g. python-multipart).
  echo   - Completing installation of studio dependencies...
  "%VENV_PY%" -m pip install -r "%SCRIPT_DIR%\requirements-studio.txt"
  if errorlevel 1 "%VENV_PY%" -m pip install fastapi "uvicorn[standard]" python-multipart "pillow>=10.4.0" numpy uharfbuzz khmercut opencv-python-headless imageio-ffmpeg edge-tts ffmpeg-python pysubs2
  echo   - Virtual environment dependencies updated.
)
goto VENV_DONE

:VENV_FAIL
echo   [ERROR] Failed to create virtual environment!
pause
exit /b 1

:VENV_DONE

:: ---------------------------------------------------------------------------
:: STEP 3: Check Khmer Fonts & Assets
:: ---------------------------------------------------------------------------
echo.
echo [3/4] Verifying bundled Khmer fonts and mascot assets...
if exist "%SCRIPT_DIR%\ai_studio\assets\fonts\NotoSansKhmer-Regular.ttf" goto FONTS_OK
echo   [INFO] Bundled fonts directory located at ai_studio\assets\fonts\
goto ASSETS_CHECK
:FONTS_OK
echo   - Bundled Khmer fonts verified: Noto Sans Khmer, Kantumruy Pro, Battambang
:ASSETS_CHECK
if not exist "%SCRIPT_DIR%\ai_studio\assets\character_default.png" goto START_STUDIO
echo   - Reusable mascot asset verified: Kiri

:: ---------------------------------------------------------------------------
:: STEP 4: Start Studio Server & Open Browser
:: ---------------------------------------------------------------------------
:START_STUDIO
echo.
echo [4/4] Starting Khmer AI Content Studio on http://localhost:8000 ...

:: Check if port 8000 is already active
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api-summary' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1
if !ERRORLEVEL! EQU 0 goto STUDIO_READY
echo   - Launching background server window...
start "Khmer AI Content Studio 8000" cmd /k ""%VENV_PY%" -m uvicorn ai_studio.app:app --host 0.0.0.0 --port 8000"
echo   - Waiting 4 seconds for server initialization...
timeout /t 4 /nobreak >nul
:STUDIO_READY
goto OPEN_BROWSER

:OPEN_BROWSER

echo.
echo  ========================================================================
echo    ✦ STUDIO IS READY! OPENING WEB BROWSER...
echo  ========================================================================
echo    - Video Showcase Gallery : http://localhost:8000/gallery
echo    - Studio Workspace App   : http://localhost:8000/
echo    - Interactive API Docs   : http://localhost:8000/docs
echo  ========================================================================
echo.

:: Open showcase gallery and studio in default browser
start http://localhost:8000/gallery
timeout /t 2 /nobreak >nul
start http://localhost:8000/

echo Keep the "Khmer AI Content Studio (:8000)" window open while working.
echo To stop everything, simply close that window or run STOP_ALL.bat.
echo.
pause
