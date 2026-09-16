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

set "STUDIO_DATA_DIR=%SCRIPT_DIR%\data\studio"
set "VENV_DIR=%SCRIPT_DIR%\.venv-studio"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

if not exist "%VENV_PY%" (
  echo [INFO] Virtual environment not found yet. Running 1_CLICK_START.bat first...
  call "%SCRIPT_DIR%\1_CLICK_START.bat"
)

if not exist "%VENV_PY%" (
  echo.
  echo [ERROR] Python virtual environment not found at %VENV_PY%
  echo         Please run 1_CLICK_START.bat first, then retry.
  goto :fail
)

REM ----------------------------------------------------------------------
REM Final MP4 paths MUST stay in sync with the gallery served by
REM ai_studio/app.py (route GET /gallery). The browser loads these exact
REM files, so any rename here must be mirrored there.
REM ----------------------------------------------------------------------
set "WHITE_MP4=outputs\love_vs_situationship_white\Love_vs_Situationship_White_Final.mp4"
set "LOVE_MP4=outputs\real_love_vs_situationship\Real_Love_vs_Situationship_Final.mp4"
set "MYTH_MP4=outputs\myth_vs_fact\Myth_vs_Fact_Final.mp4"

echo [1/3] Rendering Love vs Situationship (White Studio Edition)...
"%VENV_PY%" render_love_vs_situationship_white.py
if errorlevel 1 (
  echo [ERROR] White Studio renderer failed. See messages above.
  goto :fail
)
if not exist "%WHITE_MP4%" (
  echo [ERROR] Expected output missing: %WHITE_MP4%
  echo         The renderer finished without producing the file the gallery loads.
  goto :fail
)
echo       ✓ %WHITE_MP4%

echo.
echo [2/3] Rendering Real Love vs Situationship (Dark Compare Edition)...
"%VENV_PY%" generate_real_love_vs_situationship_video.py
if errorlevel 1 (
  echo [ERROR] Real Love vs Situationship renderer failed. See messages above.
  goto :fail
)
if not exist "%LOVE_MP4%" (
  echo [ERROR] Expected output missing: %LOVE_MP4%
  goto :fail
)
echo       ✓ %LOVE_MP4%

echo.
echo [3/3] Rendering Myth vs Fact Edition...
"%VENV_PY%" render_myth_vs_fact_video.py
if errorlevel 1 (
  echo [ERROR] Myth vs Fact renderer failed. See messages above.
  goto :fail
)
if not exist "%MYTH_MP4%" (
  echo [ERROR] Expected output missing: %MYTH_MP4%
  goto :fail
)
echo       ✓ %MYTH_MP4%

echo.
echo  ========================================================================
echo    ✓ ALL VIDEOS RENDERED SUCCESSFULLY!
echo.
echo    Gallery assets verified at:
echo      - %WHITE_MP4%
echo      - %LOVE_MP4%
echo      - %MYTH_MP4%
echo.
echo    Visible at http://localhost:8000/gallery
echo  ========================================================================
echo.
start http://localhost:8000/gallery
pause
exit /b 0

:fail
echo.
echo  ========================================================================
echo    ✗ RENDERING INCOMPLETE — fix the error above and re-run this script.
echo  ========================================================================
echo.
pause
exit /b 1
