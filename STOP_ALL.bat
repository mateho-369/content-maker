@echo off
setlocal
chcp 65001 >nul
title Auto-Clip - Stop All

echo.
echo  ======================================================
echo    AUTO-CLIP - STOP ALL SERVICES
echo  ======================================================
echo.

:: Kill by window title (the titles we used in START.bat)
echo [STOP] Trying to close service windows by title...

taskkill /FI "WINDOWTITLE eq Khmer Studio*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq ComfyUI*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq RVC*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Ollama*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Auto-Clip*" /T /F >nul 2>&1

:: Kill by port - find python processes using ports 8000,8188,9513,7865,11434
echo [STOP] Checking ports 8000, 8188, 9513, 7865, 11434...

for %%P in (8000 8188 9513 7865 11434) do (
  echo  - Checking port %%P...
  for /f "tokens=5" %%A in ('netstat -aon ^| findstr /R /C:":%%P .*LISTENING"') do (
    echo    Found PID %%A on port %%P - killing...
    taskkill /PID %%A /F >nul 2>&1
  )
)

:: Also kill any lingering python using our venvs
echo [STOP] Killing lingering python from venvs...
wmic process where "name='python.exe'" get ProcessId,CommandLine 2>nul | findstr /i "Auto-Clip-Engine ComfyUI Retrieval" >nul 2>&1
:: Use powershell for more precise kill if wmic fails on Win11
powershell -NoProfile -Command ^
  "$procs=Get-CimInstance Win32_Process -Filter \"Name='python.exe'\"; foreach($p in $procs){ $cmd=$p.CommandLine; if($cmd -match 'Auto-Clip-Engine|ComfyUI|Retrieval-based-Voice|ai_studio|main.py'){ Write-Host \"  Killing PID $($p.ProcessId): $cmd\"; Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue } }" 

echo.
echo [INFO] Remaining python processes:
tasklist /FI "IMAGENAME eq python.exe" 2>nul

echo.
echo  ======================================================
echo    STOP COMPLETE
echo    If something still runs, check Task Manager.
echo  ======================================================
pause
