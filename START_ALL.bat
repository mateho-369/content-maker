@echo off
setlocal
chcp 65001 >nul
:: This file is meant to be COPIED to C:\Users\Makara\Desktop\auto-clip\START_ALL.bat
:: If you run it from inside Auto-Clip-Engine\, it will still work and launch everything.
:: For clarity, it just calls START.bat which auto-detects sibling folders.

set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"

:: Use the PowerShell launcher because it handles service processes more reliably.
if exist "%DIR%\ai_studio\app.py" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%DIR%\START.ps1" %*
) else (
  if exist "%DIR%\Auto-Clip-Engine\START.ps1" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%DIR%\Auto-Clip-Engine\START.ps1" %*
  ) else (
    echo [ERROR] Cannot find Auto-Clip-Engine\START.ps1 at %DIR%\Auto-Clip-Engine\START.ps1
    pause
    exit /b 1
  )
)
