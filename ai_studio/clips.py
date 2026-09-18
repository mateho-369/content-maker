"""Long-video → vertical clip, served by the studio instead of a second web app.

`src/app.py` used to be its own dashboard on :8001: its own Jinja page, its own
`config.json`, its own in-memory job table, its own uvicorn process. That page is
gone — one UI, one server — but the *engine* underneath it is good and stays:
`src.highlight_engine`, `src.video_cropper`, `src.caption_generator`,
`src.voiceover_engine`. This module is the thin bridge that makes those reachable
from `ai_studio`'s API with the studio's own settings, data dir and job conventions.

Honesty rules this module keeps:
* the heavy deps (`moviepy`, mediapipe, whisper) are not installed everywhere, so
  `availability()` is asked before anything runs and the UI shows the real reason —
  a click must never spin forever because an import failed on the server;
* progress is reported per step, and a step that could not run is reported as
  `skipped` with the reason (no face model → Haar; no voiceover text → passthrough),
  exactly like the rest of the studio reports skipped work;
* files stay inside `<data>/clips/…`: only basenames are ever accepted.
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import re
import shutil
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

# what CaptionGenerator.burn_captions_opencv actually understands — the picker is
# built from this list, so the UI cannot offer a style the renderer would ignore
CAPTION_STYLES = ("Reels", "Shorts", "Tech", "None")
VIDEO_EXT = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v")
MAX_UPLOAD_MB = 4096


# ─────────────────────────────── deps / honesty ───────────────────────────────
def _spec_ok(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def availability(root: str = ".") -> Dict[str, Any]:
    """What the clip engine can do on THIS machine right now, and why not more."""
    missing: List[str] = []
    if not _spec_ok("moviepy"):
        missing.append("moviepy")
    try:
        importlib.import_module("src.highlight_engine")
    except Exception as e:                                    # noqa: BLE001
        missing.append(f"src.highlight_engine ({type(e).__name__}: {str(e)[:80]})")
    face_model = os.path.join(root, "blaze_face_short_range.tflite")
    caps = {
        "crop": _spec_ok("moviepy"),
        # mediapipe is optional: VideoCropper falls back to OpenCV's Haar cascade
        "face_model": os.path.exists(face_model),
        "whisper": _spec_ok("faster_whisper") or _spec_ok("whisper"),
        "kokoro_voice": False,
    }
    try:
        from ai_creator.voice import kokoro_available         # type: ignore
        caps["kokoro_voice"] = bool(kokoro_available())
    except Exception:
        pass
    return {
        "available": not missing,
        "missing": missing,
        "install": "pip install moviepy" + ("" if caps["whisper"] else " faster-whisper"),
        "capabilities": caps,
        "note": ("no blaze_face_short_range.tflite next to the repo — the crop falls back to "
                 "Haar-cascade face tracking" if not caps["face_model"] else ""),
        "caption_styles": list(CAPTION_STYLES),
        "max_upload_mb": MAX_UPLOAD_MB,
    }


# ─────────────────────────────────── jobs ────────────────────────────────────
def _safe_name(name: str) -> str:
    base = os.path.basename(str(name or "").replace("\\", "/"))
    if not re.fullmatch(r"[\w.\- ()\[\]]{1,180}", base) or base.startswith("."):
        raise ValueError(f"'{base or name}' is not a usable filename")
    return base


class ClipJobs:
    """In-memory job table (the clip engine is scratch work, not project state).

    Kept deliberately small and honest: a job that died with the process says so
    on the next read instead of showing a progress bar stuck at 40%.
    """

    def __init__(self) -> None:
        self._d: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def new(self, kind: str, video: str) -> str:
        jid = uuid.uuid4().hex[:8]
        with self._lock:
            self._d[jid] = {"job_id": jid, "kind": kind, "video": video,
                             "status": "queued", "stage": "waiting for a worker",
                             "progress": 0, "steps": [], "result": None, "error": None,
                             "started": time.time(), "ts": time.time()}
        return jid

    def update(self, jid: str, **kw: Any) -> None:
        with self._lock:
            j = self._d.get(jid)
            if not j:
                return
            j.update(kw)
            j["ts"] = time.time()
            steps = list(j.get("steps") or [])
            for k in ("stage", "progress", "error"):
                if k in kw:
                    steps.append({"t": round(time.time() - float(j.get("started") or time.time()), 1),
                                  k: kw[k]})
            j["steps"] = steps[-40:]

    def finish(self, jid: str, status: str, result: Any = None, error: Optional[str] = None) -> None:
        with self._lock:
            j = self._d.get(jid)
            if not j:
                return
            j.update({"status": status, "error": error, "result": result, "ts": time.time(),
                      "elapsed": round(time.time() - float(j.get("started") or time.time()), 1)})
            if status == "done":
                j["progress"], j["stage"] = 100, "done"
            elif error:
                j["stage"] = f"failed — {error[:140]}"

    def get(self, jid: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            j = self._d.get(jid)
            return dict(j) if j else None

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            return sorted((dict(v) for v in self._d.values()), key=lambda x: -float(x.get("ts") or 0))


# ───────────────────────────────── engine ────────────────────────────────────
class ClipEngine:
    """Uploads, analysis and renders for one data root, with the studio's paths."""

    def __init__(self, data_root: str) -> None:
        self.root = data_root
        self.upload_dir = os.path.join(data_root, "clips", "uploads")
        self.out_dir = os.path.join(data_root, "clips", "out")
        os.makedirs(self.upload_dir, exist_ok=True)
        os.makedirs(self.out_dir, exist_ok=True)
        self.jobs = ClipJobs()
        self._analysis: Dict[str, List[Dict[str, Any]]] = {}    # video name → highlights

    # ---- files ---------------------------------------------------------------
    def ingest(self, filename: str, raw: bytes) -> Dict[str, Any]:
        ext = os.path.splitext(str(filename or ""))[1].lower()
        if ext not in VIDEO_EXT:
            raise ValueError(f"'{ext or filename or 'nothing'}' is not a video — "
                             f"use {', '.join(VIDEO_EXT)}")
        if not raw:
            raise ValueError("the uploaded file is empty")
        if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
            raise ValueError(f"that video is {len(raw) // (1024 * 1024)} MB — keep it under "
                             f"{MAX_UPLOAD_MB} MB (or point the panel at a local file)")
        name = f"{uuid.uuid4().hex[:6]}_{_safe_name(filename)}"
        path = os.path.join(self.upload_dir, name)
        with open(path, "wb") as fh:
            fh.write(raw)
        return {"video": name, "bytes": len(raw),
                "url": f"/api/clips/source/{name}"}

    def source_path(self, name: str) -> str:
        p = os.path.join(self.upload_dir, _safe_name(name))
        if not os.path.exists(p):
            raise FileNotFoundError(f"{name} is not in {self.upload_dir}")
        return p

    def out_path(self, name: str) -> str:
        p = os.path.join(self.out_dir, _safe_name(name))
        if not os.path.exists(p):
            raise FileNotFoundError(f"{name} has not been rendered")
        return p

    def list_videos(self) -> List[Dict[str, Any]]:
        out = []
        for fn in sorted(os.listdir(self.upload_dir), reverse=True):
            p = os.path.join(self.upload_dir, fn)
            if os.path.splitext(fn)[1].lower() in VIDEO_EXT and os.path.isfile(p):
                out.append({"video": fn, "bytes": os.path.getsize(p),
                            "analyzed": bool(self._analysis.get(fn)),
                            "clips": len(self._analysis.get(fn) or []),
                            "modified": int(os.path.getmtime(p))})
        return out[:80]

    def list_outputs(self) -> List[Dict[str, Any]]:
        out = []
        for fn in sorted(os.listdir(self.out_dir), reverse=True):
            p = os.path.join(self.out_dir, fn)
            if os.path.isfile(p):
                out.append({"file": fn, "bytes": os.path.getsize(p),
                            "url": f"/api/clips/file/{fn}",
                            "modified": int(os.path.getmtime(p))})
        return out[:120]

    # ---- analyze --------------------------------------------------------------
    def analyze(self, video: str, *, top_n: int = 5, min_s: int = 15, max_s: int = 30,
                use_whisper: bool = False, whisper_model: str = "small",
                llm: Optional[Dict[str, Any]] = None) -> str:
        """Queue highlight detection; the job carries the progress (same convention
        as a render run), so a 20-minute video never blocks an HTTP request."""
        path = self.source_path(video)
        jid = self.jobs.new("analyze", video)

        def work() -> None:
            try:
                self.jobs.update(jid, status="running", stage="reading the video", progress=5)
                from src.highlight_engine import HighlightEngine       # type: ignore
                eng = HighlightEngine(path)
                opts = dict(llm or {})
                self.jobs.update(jid, stage="scoring audio energy + motion"
                                 + (" + transcript" if use_whisper else "")
                                 + (f" + {opts.get('llm_provider')}" if opts.get("llm_provider")
                                    not in (None, "", "Off") else ""), progress=25)
                hl = eng.detect_highlights(min_clip_duration=int(min_s), max_clip_duration=int(max_s),
                                           top_n=int(top_n), use_whisper=bool(use_whisper),
                                           whisper_model=str(whisper_model or "small"),
                                           llm_provider=opts.get("llm_provider", "Off"),
                                           ollama_model=opts.get("ollama_model", ""),
                                           ollama_host=opts.get("ollama_host", ""),
                                           openai_base_url=opts.get("openai_base_url", ""),
                                           openai_model=opts.get("openai_model", ""),
                                           openai_api_key=opts.get("openai_api_key"))
                clips = []
                for i, h in enumerate(hl or []):
                    clips.append({"index": i,
                                  "start": round(float(h.get("start") or 0), 2),
                                  "end": round(float(h.get("end") or 0), 2),
                                  "score": h.get("score"), "reason": h.get("reason") or h.get("why") or "",
                                  "text": str(h.get("text") or "")[:600]})
                self._analysis[video] = clips
                self.jobs.update(jid, progress=100,
                                 stage=f"{len(clips)} candidate clip(s) from a "
                                       f"{eng.duration:.0f}s video",
                                 meta={"duration": eng.duration, "fps": eng.fps,
                                      "size": [eng.width, eng.height], "timing": eng.last_timing})
                self.jobs.finish(jid, "done", result={"video": video, "clips": clips})
            except Exception as e:                                      # noqa: BLE001
                self.jobs.finish(jid, "failed", error=f"{type(e).__name__}: {e}")

        threading.Thread(target=work, daemon=True).start()
        return jid

    def highlights(self, video: str) -> List[Dict[str, Any]]:
        return list(self._analysis.get(_safe_name(video)) or [])

    # ---- export ---------------------------------------------------------------
    def export(self, video: str, index: int, *, caption_style: str = "Reels",
               track_faces: bool = True, voiceover_text: str = "",
               use_kokoro: bool = False, kokoro_voice: str = "",
               on_done: Optional[Callable[[Dict[str, Any]], None]] = None) -> str:
        path = self.source_path(video)
        clips = self.highlights(video)
        if not clips:
            raise ValueError(f"{video} has not been analyzed yet — analyze first, "
                             f"then pick one of its candidate clips")
        if not (0 <= int(index) < len(clips)):
            raise ValueError(f"clip {index} does not exist: {video} has {len(clips)} candidate(s)")
        clip = clips[int(index)]
        style = caption_style if caption_style in CAPTION_STYLES else "None"
        jid = self.jobs.new("export", video)

        def work() -> None:
            steps: List[Dict[str, Any]] = []
            try:
                cid = uuid.uuid4().hex[:6]
                cropped = os.path.join(self.out_dir, f"crop_{cid}.mp4")
                final = os.path.join(self.out_dir, f"highlight_{cid}.mp4")
                srt = os.path.join(self.out_dir, f"highlight_{cid}.srt")

                # 1 · vertical crop (the legacy app's exact step order, so a clip
                # produced here looks like one produced on :8001 before it went away)
                self.jobs.update(jid, status="running", stage="1/3 face-tracking crop", progress=5)

                def crop_progress(pct: float) -> None:
                    self.jobs.update(jid, progress=5 + int(max(0.0, min(1.0, pct / 100.0
                                                                         if pct > 1 else pct)) * 45))

                from src.video_cropper import VideoCropper                 # type: ignore
                cropper = VideoCropper(tflite_model_path="blaze_face_short_range.tflite")
                ok = cropper.crop_to_vertical(path, cropped, float(clip["start"]), float(clip["end"]),
                                              track_faces=bool(track_faces), update_progress=crop_progress)
                if not ok or not os.path.exists(cropped):
                    raise RuntimeError("the vertical crop did not produce a file")
                steps.append({"step": "crop", "ok": True, "faces": bool(track_faces)})

                # 2 · narration + ducking (skipped with a reason when there is no text)
                self.jobs.update(jid, stage="2/3 narration + ducking", progress=55)
                if str(voiceover_text or "").strip():
                    from src.voiceover_engine import VoiceoverEngine        # type: ignore
                    vo = os.path.join(self.out_dir, f"voice_{cid}.mp4")
                    if VoiceoverEngine().overlay_voiceover_on_video(
                            cropped, str(voiceover_text)[:2000], vo, duck_ratio=0.25,
                            use_kokoro=bool(use_kokoro), kokoro_voice=str(kokoro_voice or "")):
                        if os.path.exists(vo):
                            os.remove(cropped)
                            os.replace(vo, cropped)
                            steps.append({"step": "voiceover", "ok": True, "engine": "kokoro"
                                          if use_kokoro else "tts"})
                        else:
                            steps.append({"step": "voiceover", "ok": False,
                                          "why": "the overlay wrote nothing — original audio kept"})
                    else:
                        steps.append({"step": "voiceover", "ok": False,
                                      "why": "voiceover engine refused — original audio kept"})
                else:
                    steps.append({"step": "voiceover", "ok": False, "why": "no narration text given"})

                # 3 · captions + SRT
                self.jobs.update(jid, stage=f"3/3 captions ({style})", progress=75)
                from src.caption_generator import CaptionGenerator          # type: ignore
                gen = CaptionGenerator()
                timing = gen.estimate_word_timings(str(clip.get("text") or ""), 0,
                                                   max(0.5, float(clip["end"]) - float(clip["start"])))
                gen.generate_srt(timing, srt)
                burned = False
                if style != "None" and timing:
                    burned = bool(gen.burn_captions_opencv(cropped, final, timing, style_type=style))
                if not burned:
                    shutil.copy(cropped, final)
                steps.append({"step": "captions", "ok": burned, "style": style,
                              "srt": os.path.basename(srt) if os.path.exists(srt) else "",
                              **({} if burned else {"why": "burn-in unavailable — clean clip kept"})})
                if os.path.exists(cropped) and cropped != final:
                    try:
                        os.remove(cropped)
                    except OSError:
                        pass

                res = {"clip": os.path.basename(final), "clip_url": f"/api/clips/file/{os.path.basename(final)}",
                       "srt": os.path.basename(srt) if os.path.exists(srt) else "",
                       "srt_url": (f"/api/clips/file/{os.path.basename(srt)}" if os.path.exists(srt) else ""),
                       "start": clip["start"], "end": clip["end"],
                       "duration": round(float(clip["end"]) - float(clip["start"]), 2),
                       "caption_style": style, "steps": steps}
                if on_done:
                    try:
                        on_done(res)
                    except Exception:                                        # noqa: BLE001
                        pass
                self.jobs.update(jid, steps=steps)
                self.jobs.finish(jid, "done", result=res)
            except Exception as e:                                          # noqa: BLE001
                self.jobs.update(jid, steps=steps)
                self.jobs.finish(jid, "failed", error=f"{type(e).__name__}: {e}")

        threading.Thread(target=work, daemon=True).start()
        return jid
