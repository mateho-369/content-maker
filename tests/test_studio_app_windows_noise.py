"""Two studio-server behaviours from the console log.

1. Windows asyncio printed a `ConnectionResetError [WinError 10054]` traceback
   for every video range request the browser aborted — normal behaviour that
   looked like a crash and buried the real log.
2. The /gallery footers hardcoded runtimes that drifted from the rendered MP4s.
"""
import asyncio
import logging
import os
import subprocess

import pytest
from fastapi.testclient import TestClient

from ai_studio import app as app_mod

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(handler, exc=None, message=""):
    loop = asyncio.new_event_loop()
    try:
        loop.set_exception_handler(handler)
        loop.call_exception_handler({"exception": exc, "message": message})
    finally:
        loop.close()


# ------------------------------------------------- harmless disconnects stay quiet
def test_benign_disconnect_contexts_are_recognised():
    winstyle = RuntimeError("[WinError 10054] An existing connection was forcibly closed by the remote host")
    proactor = {"message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)",
                "exception": winstyle}
    assert app_mod._is_benign_client_disconnect(proactor) is True
    assert app_mod._is_benign_client_disconnect(
        {"exception": ConnectionResetError("peer went away")}) is True
    assert app_mod._is_benign_client_disconnect({"exception": BrokenPipeError("gone")}) is True
    assert app_mod._is_benign_client_disconnect({"exception": RuntimeError("boom")}) is False
    assert app_mod._is_benign_client_disconnect({}) is False


def test_quiet_handler_swallows_resets_but_keeps_real_errors(caplog):
    loop = asyncio.new_event_loop()
    try:
        app_mod.quiet_windows_connection_resets(loop)
        before = app_mod._quieted_disconnects

        with caplog.at_level(logging.ERROR, logger="asyncio"):
            loop.call_exception_handler(
                {"exception": ConnectionResetError(10054, "connection was aborted"),
                 "message": "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)"})
        assert caplog.text == "", "a client hang-up must not be logged as an error"
        assert app_mod._quieted_disconnects == before + 1

        caplog.clear()
        with caplog.at_level(logging.ERROR, logger="asyncio"):
            loop.call_exception_handler({"exception": ValueError("real bug")})
        assert "real bug" in caplog.text, "genuine errors must still be logged"
    finally:
        loop.close()


def test_quiet_handler_is_installed_once():
    loop = asyncio.new_event_loop()
    try:
        app_mod.quiet_windows_connection_resets(loop)
        first = loop.get_exception_handler()
        assert first is not None
        app_mod.quiet_windows_connection_resets(loop)
        assert loop.get_exception_handler() is first
    finally:
        loop.close()


def test_serving_app_installs_the_handler_on_startup(tmp_path):
    app = app_mod.create_app(data_root=str(tmp_path / "data"))
    seen = {}

    @app.get("/__probe_loop_handler__")
    async def probe_loop_handler():
        loop = asyncio.get_running_loop()
        seen["handler"] = loop.get_exception_handler()
        return {"patched": loop.get_exception_handler() is not None}

    with TestClient(app) as client:
        assert client.get("/__probe_loop_handler__").json()["patched"] is True
    assert seen["handler"] is not None, "the lifespan did not patch the serving loop"


# ------------------------------------------------------- /gallery runtime footer
@pytest.fixture()
def gallery_app(tmp_path, monkeypatch):
    app = app_mod.create_app(data_root=str(tmp_path / "data"))
    monkeypatch.setattr(app_mod, "ROOT", str(tmp_path), raising=True)
    monkeypatch.setattr(app_mod, "_gallery_runtime_cache", {}, raising=True)
    return app


def _make_clip(path, seconds=1.0):
    """A real (tiny) H.264 clip so media_duration() has something to probe."""
    from ai_studio.util import ffmpeg_exe
    ff = ffmpeg_exe() or "ffmpeg"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    subprocess.check_call(
        [ff, "-y", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=64x64:rate=10",
         "-pix_fmt", "yuv420p", path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def test_gallery_footer_shows_the_probed_runtime(gallery_app, tmp_path):
    out = tmp_path / "outputs"
    rel = "love_vs_situationship_white/Love_vs_Situationship_White_Final.mp4"
    _make_clip(os.path.join(str(out), rel.replace("/", os.sep)), seconds=2.0)

    with TestClient(gallery_app) as client:
        html = client.get("/gallery").text

    assert "38.41s" not in html, "stale hardcoded runtime is still in the footer"
    assert "2.00s · 720×1280" in html
    assert 'preload="none"' in html            # no speculative range fetches


def test_gallery_footer_survives_unrendered_videos(gallery_app):
    with TestClient(gallery_app) as client:
        res = client.get("/gallery")
    assert res.status_code == 200
    assert "— · 720×1280" in res.text


def test_gallery_footer_label_is_cached_per_mtime(tmp_path, monkeypatch):
    out = tmp_path / "outputs" / "myth_vs_fact"
    out.mkdir(parents=True)
    clip = out / "Myth_vs_Fact_Final.mp4"
    _make_clip(str(clip), seconds=1.0)

    monkeypatch.setattr(app_mod, "ROOT", str(tmp_path), raising=True)
    cache = {}
    monkeypatch.setattr(app_mod, "_gallery_runtime_cache", cache, raising=True)

    first = app_mod.gallery_footer_label("myth_vs_fact/Myth_vs_Fact_Final.mp4")
    assert len(cache) == 1
    second = app_mod.gallery_footer_label("myth_vs_fact/Myth_vs_Fact_Final.mp4")
    assert first == second == "1.00s · 720×1280 · H.264 / AAC"
    assert app_mod.gallery_footer_label("myth_vs_fact/Nope.mp4").startswith("—")
