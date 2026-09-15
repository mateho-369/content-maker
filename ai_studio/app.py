"""Khmer AI Content Studio — FastAPI app.

    python -m uvicorn ai_studio.app:app --host 0.0.0.0 --port 8000
    python -m ai_studio --port 8000            (same thing, opens the console line)

One process serves the API, the live status sockets and the UI, and reads/writes
nothing outside <data_dir> (default `data/studio/`) — so the whole studio can be
moved or backed up by copying that folder.
"""
import asyncio
import os
import shutil
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, config as cfg_mod, STUDIO_NAME, STUDIO_TAGLINE, api as api_mod
from .db import Database
from .events import EventBus
from .pipeline.scheduler import Scheduler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


class StudioState:
    """Shared singletons for one studio process."""

    def __init__(self, data_root=None):
        self.data_root = os.path.abspath(data_root or cfg_mod.data_root())
        os.makedirs(self.data_root, exist_ok=True)
        # Engines resolve their own model/voice dirs through config.data_root();
        # pinning the env keeps this process on one root even when settings.json
        # still points at the default repo folder.
        if os.environ.get("STUDIO_DATA_DIR") != self.data_root:
            os.environ["STUDIO_DATA_DIR"] = self.data_root
        self.settings_path = os.path.join(self.data_root, "settings.json")
        self.db = Database(os.path.join(self.data_root, "studio.db"))
        self.bus = EventBus(db=self.db)
        self.scheduler = Scheduler(self.db, self.data_root, bus=self.bus)
        self.training = {}
        self._cfg = None
        self._plan = None
        self._plan_ts = 0.0
        self._lock = threading.Lock()

    # ------------------------------------------------------------- config
    def config(self):
        with self._lock:
            if self._cfg is None:
                self._cfg = cfg_mod.load(self.settings_path)
            return cfg_mod.normalize_config(self._cfg)

    def plan(self, refresh=False, ttl=25.0):
        with self._lock:
            fresh = time.time() - self._plan_ts < ttl
            if self._plan is not None and fresh and not refresh:
                return self._plan
            cfg = cfg_mod.load(self.settings_path)
            _c, plan = cfg_mod.resolve(cfg)
            self._plan, self._plan_ts = plan, time.time()
            return plan

    def resolved_cfg(self):
        cfg = self.config()
        with self._lock:
            resolved, plan = cfg_mod.resolve(cfg)
            self._plan, self._plan_ts = plan, time.time()
        return resolved, plan

    def invalidate(self):
        with self._lock:
            self._cfg = None
            self._plan = None
            self._plan_ts = 0.0

    def seed_dirs(self):
        for sub in ("projects", "voices", "tmp", "models/tts", "models/rvc", "workflows"):
            os.makedirs(os.path.join(self.data_root, sub), exist_ok=True)


def create_app(data_root=None, enable_demo_seed=False):
    st = StudioState(data_root)
    st.seed_dirs()
    api_mod.STATE["app"] = st

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        st.bus.bind_loop(asyncio.get_running_loop())
        if enable_demo_seed:
            try:
                from .demo import seed_demo_projects

                await asyncio.to_thread(seed_demo_projects, st)
            except Exception as e:                                  # never block startup
                print(f"[studio] demo seed skipped: {e}")
        yield
        await st.scheduler.shutdown()

    app = FastAPI(title=f"{STUDIO_NAME} — {STUDIO_TAGLINE}", version=__version__,
                  lifespan=lifespan)

    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    class NoCacheStatic(StaticFiles):
        async def get_response(self, path, scope):
            r = await super().get_response(path, scope)
            r.headers["Cache-Control"] = "no-cache, must-revalidate"
            return r

    os.makedirs(STATIC_DIR, exist_ok=True)
    # bundled Khmer fonts for the web UI (same files libass burns with).
    # Mounted BEFORE /static: Starlette serves mounts in registration order,
    # so the broader /static would otherwise swallow /static/fonts.
    _fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")
    if os.path.isdir(_fonts_dir):
        app.mount("/static/fonts", NoCacheStatic(directory=_fonts_dir), name="fonts")
    _outputs_dir = os.path.join(ROOT, "outputs")
    os.makedirs(_outputs_dir, exist_ok=True)
    app.mount("/outputs", NoCacheStatic(directory=_outputs_dir), name="outputs")
    app.mount("/static", NoCacheStatic(directory=STATIC_DIR), name="static")
    app.include_router(api_mod.router)

    @app.get("/", response_class=HTMLResponse)
    async def home():
        path = os.path.join(STATIC_DIR, "index.html")
        if not os.path.exists(path):
            return HTMLResponse(f"<h1>{STUDIO_NAME}</h1><p>UI missing — run "
                                f"<code>cd ai_studio/frontend && npm ci && npm run build</code> "
                                f"or use the dev server. API at /api/status</p>")
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        # hashed Vite assets are cache-safe; index itself is never cached
        return HTMLResponse(html, headers={"Cache-Control": "no-cache, must-revalidate"})

    @app.get("/gallery", response_class=HTMLResponse)
    async def gallery():
        html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Khmer AI Studio — Video Showcase</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #0d0f12;
      color: #e2e8f0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans Khmer", sans-serif;
      padding: 24px;
      display: flex;
      flex-direction: column;
      align-items: center;
    }
    header {
      text-align: center;
      margin-bottom: 28px;
    }
    h1 {
      font-size: 26px;
      font-weight: 700;
      background: linear-gradient(135deg, #38bdf8, #818cf8, #f472b6);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 8px;
    }
    p.subtitle {
      color: #94a3b8;
      font-size: 14px;
    }
    .nav-links {
      margin-top: 12px;
      display: flex;
      gap: 16px;
      justify-content: center;
    }
    .nav-links a {
      color: #38bdf8;
      text-decoration: none;
      font-size: 13px;
      padding: 4px 12px;
      border: 1px solid rgba(56,189,248,0.3);
      border-radius: 6px;
      transition: all 0.2s;
    }
    .nav-links a:hover {
      background: rgba(56,189,248,0.1);
      border-color: #38bdf8;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
      gap: 32px;
      max-width: 900px;
      width: 100%;
    }
    .card {
      background: #161922;
      border: 1px solid #2d3748;
      border-radius: 14px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    }
    .card-header {
      padding: 16px 20px;
      border-bottom: 1px solid #2d3748;
    }
    .badge {
      display: inline-block;
      font-size: 11px;
      text-transform: uppercase;
      font-weight: 700;
      letter-spacing: 0.5px;
      padding: 3px 8px;
      border-radius: 4px;
      margin-bottom: 6px;
    }
    .badge-myth { background: #854d0e; color: #fef08a; }
    .badge-love { background: #831843; color: #fbcfe8; }
    .card-title {
      font-size: 17px;
      font-weight: 600;
      color: #f8fafc;
      line-height: 1.4;
    }
    .card-desc {
      color: #94a3b8;
      font-size: 13px;
      margin-top: 4px;
    }
    .video-wrap {
      background: #000;
      display: flex;
      justify-content: center;
      align-items: center;
      padding: 12px;
    }
    video {
      max-width: 100%;
      height: 480px;
      border-radius: 8px;
      outline: none;
      background: #000;
    }
    .card-footer {
      padding: 14px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-top: 1px solid #2d3748;
      font-size: 12px;
      color: #94a3b8;
    }
    .download-btn {
      color: #38bdf8;
      text-decoration: none;
      font-weight: 600;
    }
  </style>
</head>
<body>
  <header>
    <h1>✦ Khmer AI Content Studio — Live Showcase</h1>
    <p class="subtitle">Deterministic Vertical 9:16 Video Generation · Coeng-Safe Typography · Cute Reusable Mascot Kiri</p>
    <div class="nav-links">
      <a href="/">Open Studio App</a>
      <a href="/gallery">Showcase Gallery</a>
      <a href="/docs">FastAPI Interactive Docs</a>
      <a href="/api/character/default/asset">View Reusable Character</a>
    </div>
  </header>

  <main class="grid">
    <!-- Card 0: Love vs Situationship White Background + Internet Photos -->
    <div class="card" style="border-color: #38bdf8; box-shadow: 0 0 20px rgba(56,189,248,0.2);">
      <div class="card-header" style="background: rgba(56,189,248,0.06);">
        <span class="badge" style="background: #0284c7; color: #fff;">Featured · White Studio BG & Internet Examples</span>
        <div class="card-title">❤️ Real Love vs Situationship 💔 (White Background Studio)</div>
        <div class="card-desc">Internet Photos · Mascot Actions (Thinking/Point/Meme/CTA) · Coeng Subtitles · Free Khmer Voice</div>
      </div>
      <div class="video-wrap" style="background: #f8fafc;">
        <video controls playsinline preload="metadata">
          <source src="/outputs/love_vs_situationship_white/Love_vs_Situationship_White_Final.mp4" type="video/mp4">
          Your browser does not support the video tag.
        </video>
      </div>
      <div class="card-footer">
        <span>38.41s · 720×1280 · H.264 / AAC</span>
        <a class="download-btn" href="/outputs/love_vs_situationship_white/Love_vs_Situationship_White_Final.mp4" download>Download MP4 ↓</a>
      </div>
    </div>

    <!-- Card 1: Myth vs Fact -->
    <div class="card">
      <div class="card-header">
        <span class="badge badge-myth">Format B · Myth vs Fact</span>
        <div class="card-title">តើការផឹកទឹកកកពេលក្តៅ ធ្វើឲ្យមិនស្រួលខ្លួនពិតមែនឬ?</div>
        <div class="card-desc">Hook → Myth → Fact → Meme Reaction → Actionable CTA</div>
      </div>
      <div class="video-wrap">
        <video controls playsinline preload="metadata">
          <source src="/outputs/myth_vs_fact/Myth_vs_Fact_Final.mp4" type="video/mp4">
          Your browser does not support the video tag.
        </video>
      </div>
      <div class="card-footer">
        <span>33.48s · 720×1280 · H.264 / AAC</span>
        <a class="download-btn" href="/outputs/myth_vs_fact/Myth_vs_Fact_Final.mp4" download>Download MP4 ↓</a>
      </div>
    </div>

    <!-- Card 2: Real Love vs Situationship -->
    <div class="card">
      <div class="card-header">
        <span class="badge badge-love">Format A · Compare / Relationship</span>
        <div class="card-title">តើយើងកំពុងមាន Real Love ឬ Situationship?</div>
        <div class="card-desc">Side A vs Side B · Meme punch-in · Summary decision</div>
      </div>
      <div class="video-wrap">
        <video controls playsinline preload="metadata">
          <source src="/outputs/real_love_vs_situationship/Real_Love_vs_Situationship_Final.mp4" type="video/mp4">
          Your browser does not support the video tag.
        </video>
      </div>
      <div class="card-footer">
        <span>35.12s · 720×1280 · H.264 / AAC</span>
        <a class="download-btn" href="/outputs/real_love_vs_situationship/Real_Love_vs_Situationship_Final.mp4" download>Download MP4 ↓</a>
      </div>
    </div>
  </main>
</body>
</html>"""
        return HTMLResponse(html, headers={"Cache-Control": "no-cache, must-revalidate"})

    @app.get("/files/{relpath:path}")
    async def project_files(relpath: str, request: Request):
        """Serve anything inside the data dir (posters, clips) for the UI."""
        full = os.path.normpath(os.path.join(st.data_root, relpath))
        if not full.startswith(st.data_root) or not os.path.isfile(full):
            raise HTTPException(404, "not found")
        return FileResponse(full, headers={"Accept-Ranges": "bytes"})

    @app.get("/api-summary")
    async def summary():
        return {"studio": STUDIO_NAME, "version": __version__, "tagline": STUDIO_TAGLINE,
                "data_dir": st.data_root, "api": "/docs", "modes": ["A: Director script",
                                                                    "B: auto idea"],
                "stages": [s.key for s in __import__("ai_studio.pipeline.spec",
                                                     fromlist=["STAGES"]).STAGES]}

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        import traceback

        traceback.print_exc()
        return JSONResponse({"detail": f"{type(exc).__name__}: {exc}",
                             "hint": "see the run log / console output"}, status_code=500)

    app.state.studio = st
    return app


# Module-level app for `uvicorn ai_studio.app:app`, built lazily: importing this
# module (tests, tooling) must not create or touch the default data directory.
_lazy = {}


def __getattr__(name):                                  # PEP 562
    if name == "app":
        if "app" not in _lazy:
            _lazy["app"] = create_app()
        return _lazy["app"]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(list(globals()) + ["app"]))
