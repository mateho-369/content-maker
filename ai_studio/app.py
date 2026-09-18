"""Khmer AI Content Studio — FastAPI app.

    python -m uvicorn ai_studio.app:app --host 0.0.0.0 --port 8000
    python -m ai_studio --port 8000            (same thing, opens the console line)

One process serves the API, the live status sockets and the UI, and reads/writes
nothing outside <data_dir> (default `data/studio/`) — so the whole studio can be
moved or backed up by copying that folder.
"""
import asyncio
import errno
import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, config as cfg_mod, STUDIO_NAME, STUDIO_TAGLINE, api as api_mod
from .db import Database
from .events import EventBus
from .pipeline.scheduler import Scheduler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# Windows asyncio logs a full traceback every time a browser aborts a video
# range request (seeking, tab close, a <video> prefetch it decides it does not
# need): `_ProactorBasePipeTransport._call_connection_lost` raises
# ConnectionResetError [WinError 10054] from inside a callback, and the loop
# prints it. Nothing failed — the studio kept serving — so a /gallery page with
# three <video> tags could bury the real log under these.
_BENIGN_DISCONNECT_ERRNOS = frozenset(filter(None, (
    getattr(errno, "ECONNRESET", None),      # WinError 10054
    getattr(errno, "ECONNABORTED", None),     # WinError 10053
    getattr(errno, "EPIPE", None),
    getattr(errno, "ENOTCONN", None),
)))
_BENIGN_DISCONNECT_MARKERS = ("10053", "10054", "forcibly closed by the remote host",
                              "connection was aborted", "broken pipe")
_quieted_disconnects = 0


def _is_benign_client_disconnect(context) -> bool:
    """True when a loop exception context is just a client hanging up.

    Matches both shapes Windows produces: a real ConnectionResetError raised by
    the proactor transport, and the same failure wrapped in a plain
    RuntimeError("[WinError 10054] ...") by the callback machinery.
    """
    exc = context.get("exception")
    if isinstance(exc, ConnectionError):        # reset / aborted / broken pipe
        return True
    if isinstance(exc, OSError) and exc.errno in _BENIGN_DISCONNECT_ERRNOS:
        return True
    text = f"{exc!r} {context.get('message', '')}".lower()
    return any(marker in text for marker in _BENIGN_DISCONNECT_MARKERS)


def quiet_windows_connection_resets(loop=None):
    """Stop logging harmless client disconnects as asyncio errors.

    Safe to call more than once: a handler is only installed when the loop is
    still on the default one.
    """
    loop = loop or asyncio.get_event_loop_policy().new_event_loop()
    default_handler = loop.get_exception_handler()
    if default_handler is not None:                        # already patched
        return loop

    def handler(_loop, context):
        global _quieted_disconnects
        if _is_benign_client_disconnect(context):
            _quieted_disconnects += 1
            return
        _loop.default_exception_handler(context)

    loop.set_exception_handler(handler)
    return loop






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

    # ---------------------------------------------------------------- renders
    def final_video(self, project_id):
        """The finished MP4 for a project, or "" if it never rendered.

        Reads the asset row the assemble stage registers (`kind="final"`,
        scene_idx -1 — the burned-caption cut when captions were built, else the
        clean one), falling back to the last run's `stats.final_path` for runs
        whose asset row didn't land.

        A recorded path is returned even if the file has since been deleted:
        callers (the QA gate especially) must see that as a *broken render* and
        fail, not as "nothing to check" and pass.
        """
        a = self.db.latest_asset(project_id, "final", scene_idx=-1)
        if a and a.get("path"):
            return a["path"]
        for r in self.db.list_runs(project_id, limit=1):
            p = (r.get("stats") or {}).get("final_path") or ""
            if p:
                return p
        return ""


def create_app(data_root=None, enable_demo_seed=False):
    st = StudioState(data_root)
    st.seed_dirs()
    api_mod.STATE["app"] = st

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        loop = asyncio.get_running_loop()
        # covers `uvicorn ai_studio.app:app` (no __main__ involved)
        quiet_windows_connection_resets(loop)
        st.bus.bind_loop(loop)
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

    @app.get("/gallery", include_in_schema=False)
    async def gallery():
        """The old showcase page listed three hand-picked renders by name and had its
        own stylesheet inside this file. A gallery that cannot show YOUR videos is a
        portfolio, not a feature — so it is gone, and the link now lands on the real
        gallery panel of the one UI (which lists every project's actual final MP4)."""
        return RedirectResponse("/#gallery", status_code=302)


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
