@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title ✦ Khmer AI Content Studio — One-Click Video Renderer ✦

color 0E
echo.
echo  ========================================================================
echo    ✦ ONE-CLICK VIDEO RENDERER (Render Sample Productions) ✦
echo  ========================================================================
echo    This script runs the deterministic production renderers:
echo    [1] Love vs Situationship (White Background Studio + Internet Photos)
echo    [2] Real Love vs Situationship (Compare Format)
echo    [3] Myth vs Fact (Water Temperature Health Format)
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

echo [1/3] Rendering Love vs Situationship (White Studio Edition)...
"%VENV_PY%" render_love_vs_situationship_white.py

echo.
echo [2/3] Rendering Real Love vs Situationship (Dark Compare Edition)...
"%VENV_PY%" generate_real_love_vs_situationship_video.py

echo.
echo [3/3] Rendering Myth vs Fact Edition...
"%VENV_PY%" render_myth_vs_fact_video.py

echo.
echo  ========================================================================
echo    ✓ ALL VIDEOS RENDERED SUCCESSFULLY!
echo    Outputs saved to the outputs\ folder and visible at http://localhost:8000/gallery
echo  ========================================================================
echo.
start http://localhost:8000/gallery
pause
