@echo off
setlocal
chcp 65001 >nul
:: This file is meant to be COPIED to C:\Users\Makara\Desktop\auto-clip\START_ALL.bat
:: If you run it from inside Auto-Clip-Engine\, it will still work and launch everything.
:: For clarity, it just calls START.bat which auto-detects sibling folders.

set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"

:: If we are inside Auto-Clip-Engine, ROOT is one up, else we are already in root
if exist "%DIR%\ai_studio\app.py" (
  :: Inside Engine
  call "%DIR%\START.bat" %*
) else (
  :: Inside root auto-clip\
  if exist "%DIR%\Auto-Clip-Engine\START.bat" (
    call "%DIR%\Auto-Clip-Engine\START.bat" %*
  ) else (
    echo [ERROR] Cannot find Auto-Clip-Engine\START.bat at %DIR%\Auto-Clip-Engine\START.bat
    pause
  )
)
