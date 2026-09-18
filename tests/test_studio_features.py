"""One UI: the features the two deleted pages owned, plus the guard that keeps them gone.

`ai_creator/app.py` (a Jinja page on :8002) and `src/app.py` (the Auto-Clip dashboard
on :8001) used to be separate servers with their own HTML, their own settings file and
their own job table. The pages are deleted; the *engines* are reached through this
server now. Each test below therefore ends at a measurable API or filesystem effect —
a stored file, a written scene column, a byte count — never at "the page rendered".

Run: PYTHONPATH=. pytest tests/test_studio_features.py -q
"""
import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from ai_studio import config as cfg_mod
from ai_studio import clips as clips_mod
from ai_studio.app import StudioState, create_app

LINE = "តើអ្នកធ្លាប់ស្រលាញ់មនុស្សម្នាក់? បាទ/ចាស។"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def studio(tmp_path):
    root = str(tmp_path)
    cfg = cfg_mod.load(os.path.join(root, "settings.json"))
    cfg["video"].update({"engine": "previz", "width": 256, "height": 448, "fps": 12,
                         "max_frames": 15, "min_frames": 12})
    cfg["tts"].update({"engine": "placeholder"})
    cfg["sfx"].update({"engine": "procedural"})
    cfg["rvc"].update({"enabled": False})
    cfg["pipeline"].update({"review_gate": False, "require_qa_pass": False, "max_scenes": 3})
    cfg_mod.save(cfg, os.path.join(root, "settings.json"))
    client = TestClient(create_app(root))
    with client:
        yield client, StudioState(root), root


def _project(st, **kw):
    return st.db.create_project(title="features", mode="A", status="ready", script=LINE,
                                 topic_hint="love", content_type="explainer", **kw)["id"]


def _one_scene(client, pid):
    r = client.post(f"/api/projects/{pid}/scenes", json={"scenes": [
        {"text": LINE, "visual_prompt": "", "mood_tag": "calm", "estimated_duration_sec": 2.0,
         "audio_duration": 0, "sfx_prompt": "gentle birds chirping", "meta": {}}]})
    assert r.status_code == 200, r.text
    return r.json()["scenes"]


# ────────────────────────────────────────────────── the pages are really gone
def test_the_repo_has_exactly_one_frontend():
    """No second HTML app may creep back, and the engines they wrapped must stay.

    Asserted on the tree rather than by reviewing a diff: the last time this repo
    grew a UI it grew three, each with its own settings file — which is how you end
    up with a control that writes to a config nothing reads.
    """
    gone = ["ai_creator/app.py", "ai_creator/templates/index.html", "ai_creator/static/style.css",
            "src/app.py", "src/templates/index.html", "run_ai_creator.bat", "run_legacy_clipper.bat",
            "ai_studio/frontend/src/views/Projects.tsx"]
    for rel in gone:
        assert not os.path.exists(os.path.join(ROOT, rel)), f"{rel} came back"
    kept = ["ai_studio/frontend/src/App.tsx", "ai_studio/clips.py",
            "src/highlight_engine.py", "src/video_cropper.py", "src/caption_generator.py",
            "ai_creator/image_search.py", "ai_creator/sfx.py", "ai_creator/voice.py"]
    for rel in kept:
        assert os.path.exists(os.path.join(ROOT, rel)), f"{rel} was deleted but something needs it"
    # the studio's own server must not embed a page of its own either
    app_src = open(os.path.join(ROOT, "ai_studio", "app.py")).read()
    assert "<style>" not in app_src and app_src.count("<!doctype html>") <= 1, \
        "ai_studio/app.py is hosting markup again — that is how the fourth UI started"
    # and nothing references the deleted servers any more
    strays = []
    for dirpath, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "__pycache__", "data", ".venv")]
        for fn in files:
            if fn == os.path.basename(__file__) or not fn.endswith((".py", ".bat", ".ps1", ".md", ".txt", ".tsx")):
                continue
            p = os.path.join(dirpath, fn)
            try:
                t = open(p, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            if "ai_creator.app:" in t or "src.app:" in t or "from src.app" in t or "from ai_creator.app" in t:
                strays.append(os.path.relpath(p, ROOT))
    assert not strays, f"something still launches a deleted server: {strays}"


def test_gallery_url_redirects_into_the_single_ui(studio):
    """`/gallery` is advertised by 1_CLICK_START.bat — it must land on the real one."""
    client, _st, _root = studio
    r = client.get("/gallery", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/#gallery", (r.status_code, dict(r.headers))


# ───────────────────────────────────────────────────── gallery = the actual cuts
def test_gallery_lists_the_finished_cut_and_says_how_it_was_measured(studio):
    client, st, _root = studio
    pid = _project(st)
    _one_scene(client, pid)
    empty = client.get("/api/gallery").json()
    assert empty["items"] == [] and empty["total"] == 0, empty      # no render → no card
    run = client.post(f"/api/projects/{pid}/runs", json={"skip_stages": ["sfx"]}).json()
    for _ in range(200):
        status = client.get(f"/api/runs/{run['run_id']}/status").json()
        if status["run"]["status"] in ("completed", "partial", "failed", "cancelled"):
            break
        time.sleep(0.4)
    assert status["run"]["status"] == "completed", status["run"].get("error")

    rec = client.get("/api/gallery").json()
    assert rec["total"] >= 1, rec
    card = rec["items"][0]
    assert card["project_id"] == pid and card["title"] == "features", card
    assert not card["missing"] and card["stream_url"].startswith("/api/assets/"), card
    assert card["duration"] > 0, card
    assert card["verified"] is False and "from the render record" in rec["note"], rec["note"]

    probed = client.get("/api/gallery?probe=1").json()
    pcard = [c for c in probed["items"] if c["project_id"] == pid][0]
    assert pcard["verified"] is True and pcard["width"] and pcard["height"], pcard
    assert probed["probed"] >= 1 and "ffmpeg" in probed["note"], probed["note"]

    # and the stream really serves the file the card promises
    got = client.get(card["stream_url"])
    assert got.status_code == 200 and len(got.content) > 1000, (got.status_code, len(got.content))


def test_a_gallery_card_still_appears_when_the_file_is_gone(studio):
    """A deleted export is a fact about the project, not a reason to hide it."""
    client, st, root = studio
    pid = _project(st)
    st.db.add_asset(pid, "final", os.path.join(root, "nope.mp4"), mime="video/mp4",
                    duration=4.0, meta={"width": 256, "height": 448})
    card = client.get("/api/gallery").json()["items"][0]
    assert card["missing"] is True and card["verified"] is False, card


# ───────────────────────────────────────────────────────────── the clip engine
def test_clips_endpoints_refuse_everything_that_is_not_a_video(studio):
    client, _st, _root = studio
    d = client.get("/api/clips").json()
    for key in ("engine", "videos", "outputs", "jobs"):
        assert key in d, sorted(d)
    eng = d["engine"]
    assert isinstance(eng["available"], bool) and "missing" in eng and "install" in eng, eng
    assert eng["caption_styles"] == list(clips_mod.CAPTION_STYLES), eng

    bad = client.post("/api/clips/upload", files={"file": ("notes.txt", b"hi", "text/plain")})
    assert bad.status_code == 400 and "not a video" in bad.json()["detail"], bad.text
    empty = client.post("/api/clips/upload", files={"file": ("a.mp4", b"", "video/mp4")})
    assert empty.status_code == 400 and "empty" in empty.json()["detail"], empty.text
    assert client.post("/api/clips/analyze", json={"video": "nope.mp4"}).status_code == 404
    assert client.post("/api/clips/export", json={"video": "nope.mp4", "index": 0}).status_code in (400, 404)
    gone = client.get("/api/clips/jobs/deadbeef")
    assert gone.status_code == 404 and "memory" in gone.json()["detail"], gone.text
    # traversal: only basenames, and only inside the data dir
    for probe in ("../../etc/passwd", "..%2F..%2Fetc%2Fpasswd", "/etc/passwd"):
        r = client.get(f"/api/clips/file/{probe}")
        assert r.status_code in (400, 404), (probe, r.status_code, r.text[:80])
    assert client.get("/api/clips").json()["videos"] == [], "nothing should be stored by refused uploads"


def test_a_real_video_uploads_then_reports_honest_state(studio, tmp_path):
    """Upload + list + highlights, without needing moviepy to actually run."""
    client, _st, root = studio
    src = tmp_path / "clip.mp4"
    import subprocess
    import imageio_ffmpeg
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=size=320x240:rate=8:duration=3", "-pix_fmt", "yuv420p", str(src)],
                   check=True)
    r = client.post("/api/clips/upload", files={"file": ("clip.mp4", src.read_bytes(), "video/mp4")})
    assert r.status_code == 200, r.text
    name = r.json()["video"]
    listed = client.get("/api/clips").json()["videos"]
    assert [v["video"] for v in listed] == [name], listed
    assert listed[0]["analyzed"] is False and listed[0]["clips"] == 0, listed[0]
    assert listed[0]["bytes"] > 1000, listed[0]
    # exporting before analyzing is refused with the reason, not a 500
    pre = client.post("/api/clips/export", json={"video": name, "index": 0})
    assert pre.status_code == 400 and "analyzed" in pre.json()["detail"], pre.text
    hl = client.get(f"/api/clips/highlights/{name}").json()
    assert hl["clips"] == [] and "analyze" in hl["note"], hl
    assert client.get("/api/clips/source/" + name).status_code == 200


def test_availability_names_the_missing_extra_instead_of_failing_later(tmp_path, monkeypatch):
    """Without moviepy the panel must be switched off, not quietly broken."""
    real = clips_mod._spec_ok
    monkeypatch.setattr(clips_mod, "_spec_ok", lambda m: False if m == "moviepy" else real(m))
    a = clips_mod.availability(str(tmp_path))
    assert a["available"] is False and "moviepy" in a["missing"], a
    assert "pip install" in a["install"], a
    eng = clips_mod.ClipEngine(str(tmp_path / "d"))
    with pytest.raises(ValueError, match="not a video"):
        eng.ingest("song.mp3", b"x" * 10)
    # an unknown file is simply a missing file (the API maps that to a 404); the
    # "analyze it first" refusal is asserted through the API, where it can exist
    with pytest.raises(FileNotFoundError):
        eng.export("nothing.mp4", 0)
    # a job that never existed must not look like a job that is running
    assert eng.jobs.get("nope") is None
    jid = eng.jobs.new("export", "x.mp4")
    eng.jobs.finish(jid, "failed", error="boom")
    j = eng.jobs.get(jid)
    assert j["status"] == "failed" and "boom" in j["stage"], j


# ───────────────────────────────────────────────────────── images + sound fx
def test_image_search_labels_where_the_picture_came_from(studio):
    """CC-only, and a locally drawn fallback must never be presented as a find."""
    client, _st, root = studio
    assert client.post("/api/images/search", json={"query": "  "}).status_code == 400
    r = client.post("/api/images/search", json={"query": "rice field at dawn"}).json()
    assert r["query"] == "rice field at dawn", r
    assert r["found"] in (True, False), r
    if r["found"]:
        assert r["source"] in ("web", "ai"), r
        assert {"web": "licence", "ai": "placeholder"}[r["source"]] in r["note"], r
        got = client.get(r["url"])
        assert got.status_code == 200 and got.content[:4] == b"\x89PNG", (got.status_code, got.content[:8])
        assert os.path.dirname(os.path.join(root, r["file"])) == root, "cached outside the data dir"
    else:
        assert "note" in r and r["note"], r
    # traversal: only files inside <data>/image-cache, by basename
    assert client.get("/api/images/cache/..%2F..%2Fsettings.json").status_code in (400, 404)


def test_a_found_image_becomes_the_scene_still_it_advertises(studio):
    """The pick must land in the field the video stage reads, or the button is a lie."""
    client, st, root = studio
    pid = _project(st)
    _one_scene(client, pid)
    os.makedirs(os.path.join(root, "image-cache"), exist_ok=True)
    from PIL import Image
    Image.new("RGB", (64, 96), (20, 40, 60)).save(os.path.join(root, "image-cache", "plate.png"))

    r = client.post(f"/api/projects/{pid}/scenes/0/image-cache", json={"file": "plate.png"})
    assert r.status_code == 200, r.text
    scene = r.json()["scene"]
    assert scene["meta"]["visual_source"] == "illustration", scene["meta"]
    assert scene["meta"]["image_origin"] == "image-search:plate.png", scene["meta"]
    dst = os.path.join(root, "projects", pid, "scenes", "00", "00_custom.png")
    assert os.path.exists(dst) and os.path.getsize(dst) > 100, dst
    assert json.load(open(os.path.join(root, "projects", pid, "02_scenes.json")))["scenes"][0]["meta"]

    bad = client.post(f"/api/projects/{pid}/scenes/0/image-cache", json={"file": "../settings.json"})
    assert bad.status_code == 404, bad.text                 # refused, and nothing written
    assert client.post(f"/api/projects/{pid}/scenes/1/image-cache", json={"file": "plate.png"}).status_code == 404


def test_the_sfx_folder_the_browser_shows_is_the_folder_the_render_uses(studio):
    client, _st, _root = studio
    r = client.get("/api/sfx")
    assert r.status_code == 200, r.text
    body = r.json()
    names = [x["name"] for x in body["sfx"]]
    assert names, body
    assert all(x["url"] == f"/api/sfx/{x['name']}.wav" for x in body["sfx"]), body["sfx"][:1]
    one = client.get(f"/api/sfx/{names[0]}.wav")
    assert one.status_code == 200 and one.headers["content-type"] == "audio/wav", one.status_code
    assert len(one.content) > 44 and one.content[:4] == b"RIFF", "not a wav"
    missing = client.get("/api/sfx/definitely-not-a-sound.wav")
    assert missing.status_code == 404, missing.text


def test_sfx_assignment_survives_the_board_being_saved_again(studio):
    """The panel writes a column the board also owns: the two must agree."""
    client, st, _root = studio
    pid = _project(st)
    _one_scene(client, pid)
    names = [x["name"] for x in client.get("/api/sfx").json()["sfx"]]
    rows = [{**r, "sfx_prompt": names[0]} if r["idx"] == 0 else r
            for r in client.get(f"/api/projects/{pid}/scenes").json()["scenes"]]
    assert client.post(f"/api/projects/{pid}/scenes",
                       json={"scenes": [{k: v for k, v in r.items() if k != "idx"} for r in rows]}).status_code == 200
    again = client.get(f"/api/projects/{pid}/scenes").json()["scenes"]
    assert again[0]["sfx_prompt"] == names[0], [a["sfx_prompt"] for a in again]
    # and the sfx engine is what reads that field — no parallel channel to fall out of sync
    from ai_studio.engines import sfx as sfx_engine
    prompt = sfx_engine.prompt_for(again[0], {})
    assert names[0] in str(prompt), prompt
