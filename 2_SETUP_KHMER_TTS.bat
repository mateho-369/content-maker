@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title ✦ Khmer AI Content Studio — One-Click Khmer Voice Setup (Meta MMS) ✦

color 0A
echo.
echo  ========================================================================
echo    ✦ ONE-CLICK KHMER TTS SETUP (Meta MMS VITS - 100%% Local Voice) ✦
echo  ========================================================================
echo    This script automatically:
echo    1. Installs conversion dependencies (PyTorch CPU, onnx, Cython, scipy)
echo    2. Downloads Meta's MMS Khmer VITS checkpoint (facebook/mms-tts-khm)
echo    3. Converts it into Sherpa-ONNX format (model.onnx + tokens.txt)
echo    4. Places files into: data\studio\models\tts\vits-mms-khm\
echo    5. Runs a smoke test speaking: "បើអ្នកមិនបោះបង់ អ្នកនឹងទៅដល់។"
echo  ========================================================================
echo.

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
cd /d "%SCRIPT_DIR%"

set "VENV_DIR=%SCRIPT_DIR%\.venv-studio"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

if not exist "%VENV_PY%" (
  echo [INFO] Virtual environment not found yet. Running 1_CLICK_START.bat first...
  call "%SCRIPT_DIR%\1_CLICK_START.bat"
)

echo.
echo [START] Running PowerShell setup script (setup_khmer_tts.ps1)...
powershell -ExecutionPolicy Bypass -NoProfile -File "%SCRIPT_DIR%\scripts\setup_khmer_tts.ps1"

if %ERRORLEVEL%==0 (
  echo.
  echo  ========================================================================
  echo    ✓ SUCCESS: Meta MMS Khmer Voice is installed and ready!
  echo    Now your videos will speak with 100%% real native Khmer voiceover.
  echo  ========================================================================
) else (
  echo.
  echo  [NOTE] If compilation of monotonic_align requires C++ Build Tools,
  echo  install Visual Studio C++ Build Tools from:
  echo    https://visualstudio.microsoft.com/visual-cpp-build-tools/
  echo  Or run inside WSL (Windows Subsystem for Linux) where gcc is included.
)

echo.
pause
