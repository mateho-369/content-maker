"""Two studio-server behaviours from the console log.

1. Windows asyncio printed a `ConnectionResetError [WinError 10054]` traceback
   for every video range request the browser aborted — normal behaviour that
   looked like a crash and buried the real log.
2. The gallery hardcoded runtimes that drifted from the rendered MP4s. It is an endpoint
   now (`/api/gallery`), so these tests hold that line here: measured specs, a probe cache
   keyed by (mtime, size), and a missing file reported instead of quietly dropped.
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


# ------------------------------------------- /api/gallery: measured specs, never typed ones
def _make_clip(path, seconds=1.0):
    """A real (tiny) H.264 clip so the probe has something to measure."""
    from ai_studio.util import ffmpeg_exe
    ff = ffmpeg_exe() or "ffmpeg"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    subprocess.check_call(
        [ff, "-y", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=64x64:rate=10",
         "-pix_fmt", "yuv420p", path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@pytest.fixture()
def gallery(tmp_path):
    """A studio whose data root is a temp dir, so the gallery sees only this test's files."""
    from ai_studio import api as api_mod
    from ai_studio.app import StudioState, create_app
    root = str(tmp_path / "data")
    api_mod._GALLERY_PROBE_CACHE.clear()
    with TestClient(create_app(root)) as client:
        client.st = StudioState(root)
        client.root = root
        yield client


def _final(client, rel, seconds=2.0, width=64, height=64, exists=True):
    st = client.st
    pid = st.db.create_project(title="gallery probe", mode="A", status="done",
                              script="line", settings={})["id"]
    path = os.path.join(client.root, rel)
    if exists:
        _make_clip(path, seconds=seconds)
    st.db.add_asset(pid, "final", path, stage="assemble", mime="video/mp4", duration=seconds,
                    meta={"width": width, "height": height})
    return pid, path


def _card(client, pid, query="?probe=1"):
    items = client.get("/api/gallery" + query).json()["items"]
    return [c for c in items if c["project_id"] == pid][0]


def test_gallery_reports_the_measured_runtime(gallery):
    """What a card claims comes from the file, not from a string in the source."""
    pid, _path = _final(gallery, "outputs/probe.mp4", seconds=2.0)
    card = _card(gallery, pid)
    assert card["verified"] is True and abs(float(card["duration"]) - 2.0) < 0.35, card
    assert (card["width"], card["height"]) == (64, 64), card
    # without ?probe=1 the same card is still honest about where its numbers came from
    lazy = _card(gallery, pid, query="")
    assert lazy["verified"] is False and "render record" in gallery.get("/api/gallery").json()["note"], lazy


def test_gallery_survives_a_cut_that_went_missing(gallery):
    """A deleted export is a fact about the project — listed and labelled, never hidden."""
    pid, _ = _final(gallery, "outputs/gone.mp4", seconds=9.0, width=1080, height=1920, exists=False)
    card = _card(gallery, pid)
    assert card["missing"] is True and card["verified"] is False, card
    assert card["duration"] == 9.0 and (card["width"], card["height"]) == (1080, 1920), card


def test_the_probe_is_cached_until_the_file_changes(gallery, monkeypatch):
    """Cached because re-opening every export per paint is what made the gallery slow;
    keyed by (mtime, size) so a re-render is measured again."""
    from ai_studio import api as api_mod
    pid, path = _final(gallery, "outputs/cached.mp4", seconds=1.0)
    assert _card(gallery, pid)["verified"] is True
    assert path in api_mod._GALLERY_PROBE_CACHE, list(api_mod._GALLERY_PROBE_CACHE)

    calls = {"n": 0}
    real = api_mod._gallery_probe

    def spy(p):
        calls["n"] += 1
        return real(p)

    monkeypatch.setattr(api_mod, "_gallery_probe", spy)
    assert _card(gallery, pid)["verified"] is True
    assert calls["n"] == 1, "the cached answer must be returned without touching ffmpeg"

    _make_clip(path, seconds=3.0)                       # re-render into the same path
    assert _card(gallery, pid)["verified"] is True      # cache key no longer matches
    assert calls["n"] == 2, "a changed file must be measured again"
    card = _card(gallery, pid)
    assert abs(float(card["duration"]) - 3.0) < 0.35, card


def test_a_hardcoded_runtime_cannot_come_back():
    """The page used to print 38.41s for a two-second video; that string is dead."""
    for rel in ("ai_studio/app.py", "ai_studio/api.py"):
        text = open(os.path.join(REPO_ROOT, rel)).read()
        assert "38.41s" not in text, rel
