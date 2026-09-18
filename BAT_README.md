# Auto-Clip - One-Click BAT Launchers

These `.bat` files auto-run the whole stack on Windows. Place is `C:\Users\Makara\Desktop\auto-clip\`.

## Folder layout expected

```
auto-clip\
  Auto-Clip-Engine\          <- this repo (contains all .bat files)
    START.bat                <- MASTER: launches everything
    setup_all.bat            <- first-time full setup
    run_studio.bat           <- only Khmer Studio :8000
    run_comfyui.bat          <- only ComfyUI :8188
    run_rvc.bat              <- only RVC :9513/:7865
    check_system.bat         <- diagnostics + readiness report
    STOP_ALL.bat             <- kill all services
    START_ALL_FROM_ROOT.bat  <- copy this to auto-clip\START_ALL.bat
  ComfyUI\                   <- https://github.com/comfyanonymous/ComfyUI
    main.py
    .venv\  (its own venv)
    models\
    custom_nodes\ComfyUI-MMAudio\
  Retrieval-based-Voice-Conversion-WebUI\
    infer-web.py / api.py / webui.py
    .venv\
  START_ALL.bat              <- (copy of START_ALL_FROM_ROOT) lives in auto-clip root for double-click

  .claude\  .vscode\  claude-code-setup-task.md etc - not needed to run
```

## Quick Start (first time)

1. **Install prerequisites (once):**
   - Python 3.11 (tick Add to PATH): https://python.org
   - Git: https://git-scm.com
   - ffmpeg: `winget install Gyan.FFmpeg`
   - Ollama: `winget install Ollama.Ollama`
   - Node.js 18+ (for frontend build): https://nodejs.org
   - VS Build Tools (for Khmer TTS compilation, optional)

2. **Double-click `setup_all.bat`** in `Auto-Clip-Engine\`
   - Creates `.venv-studio` + installs `requirements-studio.txt`
   - Builds frontend `ai_studio/frontend -> ai_studio/static/` if npm present
   - Creates ComfyUI `.venv` + installs its requirements + clones MMAudio node
   - Creates RVC `.venv` + installs requirements
   - Pulls Ollama models `sailor2:8b` and `llama3.2:3b`
   - Optional Khmer TTS setup (sherpa-onnx)

3. **Double-click `START.bat`** (or `..\START_ALL.bat` from root)
   - Launches Ollama if not running
   - Launches ComfyUI :8188 in new window
   - Launches RVC API :9513 / Gradio :7865 in new window
   - Runs `python -m ai_studio --check` readiness report
   - Launches Khmer Studio :8000 in new window
   - Opens http://localhost:8000/ in browser

## Daily Use

- **One click:** `START.bat` or `auto-clip\START_ALL.bat`
- **Check health:** `check_system.bat`
- **Stop all:** `STOP_ALL.bat`

## What each service does

| Service | Port | Folder | Start command (what BAT does) | If missing |
|---------|------|--------|-------------------------------|------------|
| Ollama | 11434 | system | `ollama serve` | Studio uses deterministic fallback (no LLM) |
| ComfyUI | 8188 | `..\ComfyUI` | `.venv\Scripts\python.exe main.py --listen 127.0.0.1 --port 8188` | video=SFX uses previz/procedural draft |
| RVC WebUI | 9513 / 7865 | `..\Retrieval...` | `api.py --port 9513` or `infer-web.py --p 7865` | timbre bypass (base Khmer voice) |
| Khmer Studio | 8000 | `Auto-Clip-Engine` | `.venv-studio\Scripts\python.exe -m ai_studio --port 8000` | main UI |

## Manual checks

```bat
curl http://127.0.0.1:11434/api/tags      :: Ollama models
curl http://127.0.0.1:8188/system_stats   :: ComfyUI GPU
curl http://127.0.0.1:8000/api/status     :: Studio readiness JSON
curl http://127.0.0.1:9513/               :: RVC API
```

## Troubleshooting

- **Port busy:** `STOP_ALL.bat` then `START.bat`. Or change port: `run_studio.bat 8002`
- **Frontend empty:** `cd ai_studio\frontend && npm ci && npm run build`
- **ComfyUI OOM 8GB:** edit `run_comfyui.bat` uncomment `--lowvram`
- **torch.cuda.is_available() False:** reinstall torch CUDA trio together:
  ```
  pip install torch==2.7.1+cu128 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128 --force-reinstall
  ```
- **Ollama slow:** `ollama pull sailor2:8b` once, keep `num_ctx 4096`
- **Studio shows previz:** ComfyUI not running or model files missing - see `README-STUDIO.md` ComfyUI models section
- **RVC bypass:** No trained voice yet - normal. Train via Studio UI -> Voices, or import .pth

## Flags for START.bat

```
START.bat --studio-only   :: only studio, no Comfy/RVC/Ollama
START.bat --no-comfy      :: skip ComfyUI
START.bat --no-rvc        :: skip RVC
START.bat --no-ollama     :: skip Ollama check
```

## The two legacy launchers are gone

`run_ai_creator.bat` (:8002) and `run_legacy_clipper.bat` (:8001) launched separate Jinja
front-ends with their own settings files. Both pages are deleted; the engines they wrapped
are panels of the studio now:

- AI-team planner, characters, voices, image search, SFX library -> the studio's own panels;
- long-video clipping -> **Clip a video** in the studio rail (⌘C).

`run.bat` / `start.bat` (headless clip runs) are untouched and still write to `output/`.

## For PowerShell users

`setup-studio.ps1` still works: `powershell -ExecutionPolicy Bypass -File .\setup-studio.ps1 -WithTts`

## Security

All services bind to 127.0.0.1 / 0.0.0.0 local only, no auth. Do NOT expose to public internet. Put behind Tailscale if remote needed.
