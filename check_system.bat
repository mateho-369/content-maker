@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Auto-Clip - System Check
set "ENGINE_DIR=%~dp0"
if "%ENGINE_DIR:~-1%"=="\" set "ENGINE_DIR=%ENGINE_DIR:~0,-1%"
set "ROOT_DIR=%ENGINE_DIR%\.."
set "COMFY_DIR=%ROOT_DIR%\ComfyUI"
set "RVC_DIR=%ROOT_DIR%\Retrieval-based-Voice-Conversion-WebUI"

set "STUDIO_PY="
if exist "%ENGINE_DIR%\.venv-studio\Scripts\python.exe" set "STUDIO_PY=%ENGINE_DIR%\.venv-studio\Scripts\python.exe"
if not defined STUDIO_PY if exist "%ENGINE_DIR%\.venv\Scripts\python.exe" set "STUDIO_PY=%ENGINE_DIR%\.venv\Scripts\python.exe"
if not defined STUDIO_PY if exist "%ENGINE_DIR%\venv\Scripts\python.exe" set "STUDIO_PY=%ENGINE_DIR%\venv\Scripts\python.exe"
if not defined STUDIO_PY (
  where python >nul 2>&1
  if !ERRORLEVEL!==0 set "STUDIO_PY=python"
)

echo.
echo  ======================================================
echo    AUTO-CLIP - SYSTEM CHECK
echo  ======================================================
echo.

:: Python
echo [1] Python
if defined STUDIO_PY (
  "%STUDIO_PY%" --version
) else (
  echo  NOT FOUND
)
where py >nul 2>&1 && py --version
echo.

:: ffmpeg
echo [2] ffmpeg
where ffmpeg >nul 2>&1
if %ERRORLEVEL%==0 (
  ffmpeg -version | findstr /i "ffmpeg version"
) else (
  echo  NOT FOUND on PATH - checking imageio-ffmpeg fallback...
  if defined STUDIO_PY "%STUDIO_PY%" -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())" 2>nul
)
echo.

:: Node / npm for frontend
echo [3] Node.js (for frontend build)
where node >nul 2>&1
if %ERRORLEVEL%==0 (node --version) else (echo  NOT FOUND - frontend build will skip)
where npm >nul 2>&1
if %ERRORLEVEL%==0 (npm --version) else (echo  npm NOT FOUND)
if exist "%ENGINE_DIR%\ai_studio\static\assets" (
  echo  Frontend built: YES - %ENGINE_DIR%\ai_studio\static\assets
  dir /b "%ENGINE_DIR%\ai_studio\static\assets" | findstr /c:"index-"
) else (
  echo  Frontend built: NO - run setup_all.bat or npm run build
)
echo.

:: Ollama
echo [4] Ollama :11434
where ollama >nul 2>&1
if %ERRORLEVEL%==0 (
  echo  Installed: YES
  ollama --version 2>nul
  powershell -NoProfile -Command "try { $r=Invoke-WebRequest -Uri http://127.0.0.1:11434/api/tags -TimeoutSec 3 -UseBasicParsing; Write-Host '  Running: YES'; $j=$r.Content | ConvertFrom-Json; $j.models | ForEach-Object { Write-Host ('   - '+$_.name) } } catch { Write-Host '  Running: NO - run ollama serve' }"
) else (
  echo  NOT INSTALLED - winget install Ollama.Ollama
)
echo.

:: ComfyUI
echo [5] ComfyUI :8188
if exist "%COMFY_DIR%\main.py" (
  echo  Found: YES at %COMFY_DIR%
  powershell -NoProfile -Command "try { Invoke-WebRequest -Uri http://127.0.0.1:8188/system_stats -TimeoutSec 3 -UseBasicParsing | Out-Null; Write-Host '  Running: YES' } catch { Write-Host '  Running: NO' }"
  echo  Models check:
  if exist "%COMFY_DIR%\models\diffusion_models" (
    dir /b "%COMFY_DIR%\models\diffusion_models" 2>nul
  ) else (
    echo   diffusion_models folder missing
  )
  if exist "%COMFY_DIR%\custom_nodes\ComfyUI-MMAudio" (
    echo   ComfyUI-MMAudio: YES
  ) else (
    echo   ComfyUI-MMAudio: NO - git clone https://github.com/kijai/ComfyUI-MMAudio custom_nodes/ComfyUI-MMAudio
  )
) else (
  echo  NOT FOUND at %COMFY_DIR%
)
echo.

:: RVC
echo [6] RVC WebUI :9513 / :7865
if exist "%RVC_DIR%" (
  echo  Found: YES at %RVC_DIR%
  powershell -NoProfile -Command "try { Invoke-WebRequest -Uri http://127.0.0.1:9513/ -TimeoutSec 2 -UseBasicParsing | Out-Null; Write-Host '  API :9513 Running: YES' } catch { Write-Host '  API :9513 Running: NO' }"
  powershell -NoProfile -Command "try { Invoke-WebRequest -Uri http://127.0.0.1:7865/ -TimeoutSec 2 -UseBasicParsing | Out-Null; Write-Host '  Gradio :7865 Running: YES' } catch { Write-Host '  Gradio :7865 Running: NO' }"
) else (
  echo  NOT FOUND at %RVC_DIR%
)
echo.

:: Studio
echo [7] Khmer Studio :8000
if defined STUDIO_PY (
  powershell -NoProfile -Command "try { Invoke-WebRequest -Uri http://127.0.0.1:8000/api/health -TimeoutSec 2 -UseBasicParsing | Out-Null; Write-Host '  Running: YES - http://localhost:8000/' } catch { Write-Host '  Running: NO' }"
  echo.
  echo  Readiness report:
  "%STUDIO_PY%" -m ai_studio --check
) else (
  echo  No python to run check
)
echo.

:: GPU
echo [8] GPU / VRAM
where nvidia-smi >nul 2>&1
if %ERRORLEVEL%==0 (
  nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv
) else (
  echo  nvidia-smi not found - no NVIDIA GPU or driver missing
)
if defined STUDIO_PY (
  "%STUDIO_PY%" -c "import torch; print(f\"  torch {torch.__version__} cuda_available={torch.cuda.is_available()} device_count={torch.cuda.device_count() if hasattr(torch.cuda,'device_count') else '?'}\")" 2>nul
)
echo.

echo  ======================================================
echo    END OF CHECK - See README-STUDIO.md for fixes
echo  ======================================================
pause
