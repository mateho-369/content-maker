@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Auto-Clip - Model Install Helper
set "ENGINE_DIR=%~dp0"
if "%ENGINE_DIR:~-1%"=="\" set "ENGINE_DIR=%ENGINE_DIR:~0,-1%"
set "ROOT_DIR=%ENGINE_DIR%\.."
set "COMFY_DIR=%ROOT_DIR%\ComfyUI"

echo.
echo  ======================================================
echo    MODEL INSTALL HELPER
echo  ======================================================
echo    This helps you place ComfyUI models correctly.
echo    See README-STUDIO.md for full list + links.
echo  ======================================================
echo.

echo [INFO] ComfyUI dir: %COMFY_DIR%
if not exist "%COMFY_DIR%\main.py" (
  echo [ERROR] ComfyUI not found at %COMFY_DIR%
  pause
  exit /b 1
)

echo.
echo  Required model folders (will be created if missing):
for %%D in (
  "models\diffusion_models"
  "models\vae"
  "models\clip"
  "models\mmaudio"
  "models\unet"
  "models\checkpoints"
) do (
  if not exist "%COMFY_DIR%\%%D" mkdir "%COMFY_DIR%\%%D"
  echo   - %COMFY_DIR%\%%D
)

echo.
echo  Expected files (place manually, links in README-STUDIO.md):
echo    models/diffusion_models/wan2.1_t2v_1.3b_bf16.safetensors  [OR wan2.2_ti2v_5B_fp16.safetensors]
echo    models/vae/wan_2.1_vae.safetensors  [or wan2.2_vae.safetensors]
echo    models/clip/umt5_xxl_fp8_e4m3fn_scaled.safetensors
echo    models/mmaudio/mmaudio_small_08_44k_v2.safetensors
echo    models/mmaudio/mmaudio_vae_44k_fp16.safetensors
echo    models/mmaudio/mmaudio_synchformer_fp16.safetensors
echo    models/mmaudio/apple_DFN5B-CLIP-ViT-H-14-384_fp16.safetensors
echo    models/mmaudio/bigvgan_v2_44khz_128band_512x/  (vocoder folder)
echo    models/unet/flux2-klein-4b-fp8.safetensors  (for illustrations)
echo.

echo  Checking what you already have:
for %%F in (
  "%COMFY_DIR%\models\diffusion_models\*.safetensors"
  "%COMFY_DIR%\models\vae\*.safetensors"
  "%COMFY_DIR%\models\clip\*.safetensors"
  "%COMFY_DIR%\models\mmaudio\*.safetensors"
  "%COMFY_DIR%\models\unet\*.safetensors"
) do (
  if exist %%F (
    for %%A in (%%F) do echo   [OK] %%~nxA - %%~zA bytes
  )
)

echo.
echo  --- Studio data dir ---
set "STUDIO_PY="
if exist "%ENGINE_DIR%\.venv-studio\Scripts\python.exe" set "STUDIO_PY=%ENGINE_DIR%\.venv-studio\Scripts\python.exe"
if defined STUDIO_PY (
  "%STUDIO_PY%" -c "import os; from ai_studio.config import data_root; print(data_root())" 2>nul
  echo    models/tts/vits-mms-khm/  (Khmer TTS - run scripts\setup_khmer_tts.ps1)
  echo    models/rvc/  (your .pth + assets/*.index)
)

echo.
echo  --- Ollama ---
where ollama >nul 2>&1
if %ERRORLEVEL%==0 (
  ollama list
) else (
  echo  Ollama not installed
)

echo.
echo  Done. Download models from:
echo    Wan: https://huggingface.co/Wan-AI/Wan2.1-T2V-1.3B
echo    Wan2.2: https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B
echo    MMAudio: https://huggingface.co/hkcheng/MMAudio
echo    FLUX.2 klein: https://huggingface.co/black-forest-labs/FLUX.2-klein-4B
echo.
pause
