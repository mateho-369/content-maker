"""The studio QA gate endpoint (`GET /api/qa/project/{id}`) and `StudioState.final_video`.

Three defects, all of which made the panel lie to the user:

1. 404 "Project or scenes not found" for a project that exists but has no scenes
   yet. `final_video()` returned "" for any project whose latest run was not
   `completed` — i.e. every draft — and the panel called the endpoint on mount, so
   the page threw while rendering (`Cannot read properties of undefined (reading
   'some')`). A draft is a normal state: it answers 200 with `pending: true` and a
   message naming what is missing. 404 stays for a project that does not exist.
2. The gate approved files it had never opened: `final_video` accepted any
   ≥1 KB `final.mp4`, and `validate_final_mp4` reported `mp4_checked` from the
   *path*, so a truncated or bogus export went green. It now opens the container
   (`media.probe`) and reports duration, streams and resolution.
3. `mp4_checked: True` was hardcoded in the response — it claimed a verification
   that never ran. It now means "the container was actually parsed", which is
   False both for a file that is gone and for junk ffmpeg cannot read.

Run: PYTHONPATH=. pytest tests/test_studio_qa_endpoint.py -q
"""
import os
import subprocess

import pytest
from fastapi.testclient import TestClient

from ai_studio import config as cfg_mod
from ai_studio.app import StudioState, create_app
from ai_studio.media import probe
from ai_studio.qa import run_full_project_qa, validate_final_mp4

LINE = "តើអ្នកធ្លាប់ស្រលាញ់មនុស្សម្នាក់?"


@pytest.fixture()
def studio(tmp_path):
    st = StudioState(str(tmp_path))
    cfg = st.config()
    cfg["video"].update({"width": 320, "height": 560, "fps": 8, "steps": 4,
                         "max_frames": 8, "min_frames": 8})
    cfg["assembly"]["fps"] = 8
    cfg["tts"]["engine"] = "placeholder"
    cfg_mod.save(cfg, st.settings_path)
    st.invalidate()
    return st, TestClient(create_app(str(tmp_path)))


def tmpdir_of(st):
    """Scratch space inside the studio's own (already temp) data dir."""
    return st.data_root


def _project_with_scenes(st, texts=(LINE, "ប៉ុន្តែគេស្រលាញ់ម៉ាស៊ីនវិញ។"), **kw):
    kw.setdefault("script", " ".join(texts))
    kw.setdefault("mode", "A")
    kw.setdefault("status", "review")
    pid = st.db.create_project(title="qa", **kw)["id"]
    st.db.replace_scenes(pid, [{"text": t, "idx": i, "estimated_duration_sec": 2.0,
                                "visual_prompt": "a field at dawn", "mood_tag": "calm-warm",
                                "audio_duration": 0.0} for i, t in enumerate(texts)])
    return pid


# ------------------------------------------------------------------ the 404 fix
def test_draft_project_with_no_scenes_is_pending_not_404(studio):
    st, client = studio
    pid = st.db.create_project(title="untouched", mode="A", status="draft")["id"]
    r = client.get(f"/api/qa/project/{pid}")
    assert r.status_code == 200, r.text
    d = r.json()
    # the panel reads these unguarded, so every key must exist — empty is fine,
    # absent used to crash the whole view
    for key in ("pending", "approved", "failures", "warnings", "fail_count", "warn_count",
                "total_scenes", "mp4_checked", "mp4_verified", "checked", "message"):
        assert key in d, f"panel would read undefined.{key}"
    assert d["pending"] is True and d["approved"] is False
    assert d["failures"] == [] and d["warnings"] == [] and d["checked"] == 0
    # the message names what is actually missing — no generic "check the render"
    assert "no script yet" in d["message"]
    st.db.update_project(pid, script=LINE)
    assert "no scenes yet" in client.get(f"/api/qa/project/{pid}").json()["message"]


def test_unknown_project_is_still_a_404(studio):
    _st, client = studio
    r = client.get("/api/qa/project/nope123")
    assert r.status_code == 404
    assert "project not found" in r.json()["detail"]


def test_no_message_tells_the_user_to_check_a_render_that_has_not_run(studio):
    """`final_video()` is '' before a completed run, so the old copy said
    'check the render first' *before the render had run*."""
    st, client = studio
    pid = _project_with_scenes(st)                      # scenes, no render yet
    d = client.get(f"/api/qa/project/{pid}").json()
    assert d["pending"] is False and d["approved"] is False
    assert d["final_mp4"] == "" and d["mp4_checked"] is False
    blob = " ".join([d.get("message", "")] + [x["issue"] for x in d["failures"] + d["warnings"]])
    assert "check the render first" not in blob
    assert "no rendered video yet" in d["message"] and "Assemble" in d["message"]
    assert any("not been assembled" in x["issue"] or "no final MP4 on record" in x["issue"]
               for x in d["failures"]), d["failures"]


# ----------------------------------------------------------------- the fake-pass
def test_the_gate_actually_opens_the_rendered_mp4(studio):
    st, client = studio
    pid = _project_with_scenes(st)
    bogus = os.path.join(st.data_root, "projects", pid, "scenes", "00", "final.mp4")
    os.makedirs(os.path.dirname(bogus), exist_ok=True)
    junk = b"not an mp4 at all" * 400                   # ~6 KB: the size check passed it
    with open(bogus, "wb") as f:
        f.write(junk)
    st.db.add_asset(pid, "final", bogus, stage="assemble", scene_idx=-1)

    d = client.get(f"/api/qa/project/{pid}").json()
    assert d["final_mp4"] == bogus
    assert d["final_size_bytes"] == len(junk)           # reported, but not a verdict
    assert d["mp4_checked"] is False, "nothing parsed → nothing checked"
    assert d["mp4_verified"] is False and d["approved"] is False
    assert any("not a readable MP4" in x["issue"] for x in d["failures"]), d["failures"]


def test_a_real_render_is_reported_as_checked(studio):
    """The other side: with a genuine file the gate says it checked — and a silent
    render still fails, even though ffmpeg parsed it fine."""
    st, client = studio
    pid = _project_with_scenes(st)
    silent = write_test_mp4(os.path.join(tmpdir_of(st), "silent.mp4"), audio=False)
    st.db.add_asset(pid, "final", silent, stage="assemble", scene_idx=-1)
    d = client.get(f"/api/qa/project/{pid}").json()
    assert d["mp4_checked"] is True and d["mp4_verified"] is False
    assert any("no audio stream" in x["issue"] for x in d["failures"]), d["failures"]


def test_a_render_recorded_but_missing_from_disk_fails(studio):
    """The ghost path: the asset row says the render exists, the file is gone.
    `final_video` returns the path; the gate must not call that a pass."""
    st, client = studio
    pid = _project_with_scenes(st)
    ghost = os.path.join(tmpdir_of(st), "gone", "run1.mp4")
    st.db.add_asset(pid, "final", ghost, stage="assemble", scene_idx=-1)

    d = client.get(f"/api/qa/project/{pid}").json()
    assert d["final_mp4"] == ghost
    assert d["mp4_verified"] is False and d["mp4_checked"] is False
    assert d["approved"] is False
    assert any("not on disk" in x["issue"] for x in d["failures"]), d["failures"]


# ------------------------------------------------------------------ probe contract
def write_test_mp4(path, *, seconds=1.0, size=(160, 288), audio=True, rate=44100):
    """Encode a real clip with imageio-ffmpeg's bundled binary (no system ffmpeg
    on this box); `audio` is written at 16 kHz mono and muxed by ffmpeg."""
    import numpy as np

    ff = cfg_ffmpeg()
    frames = int(seconds * 8)
    tmp = path + ".npy"
    arr = np.zeros((frames, size[1], size[0], 3), dtype=np.uint8)
    arr[..., 0] = 40
    np.save(tmp, arr)
    src = os.path.join(os.path.dirname(path), "src.mp4")
    subprocess.run([ff, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s",
                    f"{size[0]}x{size[1]}", "-r", "8", "-i", "-", "-c:v", "libx264",
                    "-preset", "ultrafast", "-pix_fmt", "yuv420p", src],
                   input=arr.tobytes(), check=True, capture_output=True)
    if not audio:
        os.replace(src, path)
        os.remove(tmp)
        return path
    import numpy as np
    from ai_studio.util import write_wav

    wav = os.path.join(os.path.dirname(path), "a.wav")
    n = int(seconds * rate)
    tone = 0.3 * np.sin(2 * np.pi * 220.0 * np.arange(n) / rate)
    write_wav(wav, tone.tolist(), rate)
    subprocess.run([ff, "-y", "-i", src, "-i", wav, "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", "aac", "-shortest", path], check=True,
                   capture_output=True)
    for p in (tmp, src, wav):
        try:
            os.remove(p)
        except OSError:
            pass
    return path


def cfg_ffmpeg():
    from ai_studio.util import ffmpeg_exe
    return ffmpeg_exe()


def test_probe_media_reports_what_it_actually_saw(tmp_path):
    """`probe` is the gate's only source of truth about the export, so its two
    failure modes must stay distinguishable: nothing to look at (size 0, no
    streams, probe_used False) vs a file it could parse. And a probed file always
    reports duration + streams + size."""
    silent = write_test_mp4(str(tmp_path / "silent.mp4"), audio=False)
    talking = write_test_mp4(str(tmp_path / "talk.mp4"))
    ghost = str(tmp_path / "nope.mp4")

    p = probe(ghost)
    assert not p["duration"] and not p["width"] and p["size_bytes"] == 0
    assert p["probe_used"] is False and p["video_stream"] is None

    v = probe(silent)
    assert v["probe_used"] is True and v["duration"] > 0
    assert v["size_bytes"] == os.path.getsize(silent)
    assert v["video_stream"] and (v["video_stream"]["width"], v["video_stream"]["height"]) == (160, 288)
    assert not v["audio_stream"], "this fixture has no audio track — that is the point"
    assert v["has_audio"] is False

    a = probe(talking)
    assert a["audio_stream"] and a["audio_stream"]["sample_rate"] == 44100
    assert a["has_audio"] is True

    # the gate's own verdicts, on the same files
    assert validate_final_mp4(silent)["passed"] is False
    assert validate_final_mp4(talking)["passed"] is True


def test_final_dimensions_reads_the_project_not_a_constant():
    from ai_studio.qa import final_dimensions
    assert final_dimensions({"video": {"width": 1080, "height": 1920}}) == (1080, 1920)
    assert final_dimensions({}) is None
    assert final_dimensions(None) is None
    assert final_dimensions({"video": {"width": "nope", "height": 560}}) is None
    res = validate_final_mp4.__defaults__
    assert res == (None,), "expect must default to 'no expectation', not a hardcoded 9:16"


def test_only_a_short_export_is_a_missing_scene():
    """Assembly pads a clip to the scene's planned length, so an over-long cut is
    normal and an audio-vs-video diff is noise. A cut SHORTER than the board is the
    only length fact worth failing on — and it needs both sides to be real."""
    import tempfile

    scenes = [{"text": LINE, "idx": 0, "estimated_duration_sec": 3.0, "audio_duration": 0.0},
              {"text": "ម្ខាងទៀត។", "idx": 1, "estimated_duration_sec": 3.0, "audio_duration": 0.0}]
    tmp = tempfile.mkdtemp()

    # no render at all → nothing to compare, no invented failure
    assert not [f for f in run_full_project_qa(scenes, "", content_type="explainer")["failures"]
                if f["check"] == "sync"]

    short = write_test_mp4(os.path.join(tmp, "short.mp4"), seconds=1.0, audio=True)
    hits = [f for f in run_full_project_qa(scenes, short, content_type="explainer")["failures"]
            if f["check"] == "sync"]
    assert len(hits) == 1, hits
    assert "missing" in hits[0]["issue"] and "planned 6.0s" in hits[0]["issue"]

    # same board, a cut that runs long (padded previews) → no failure
    long_cut = write_test_mp4(os.path.join(tmp, "long.mp4"), seconds=8.0, audio=True)
    assert not [f for f in run_full_project_qa(scenes, long_cut, content_type="explainer")["failures"]
                if f["check"] == "sync"]


# ------------------------------------------------------------- the 500 on /settings
def test_the_tts_style_route_survives_a_missing_edge_tts(studio):
    """`/api/tts/providers-and-styles` answered 500 for a reason unrelated to
    edge_tts: it read `st.cfg`, and StudioState exposes `config()` — so the Voice
    tab could never load. Same class of bug as the QA 404: the endpoint assumed a
    shape its own state object does not have. (The optional dependency itself is
    fine to miss: `edge_tts_provider` is imported lazily.)"""
    _st, client = studio
    r = client.get("/api/tts/providers-and-styles")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["providers"], list) and body["providers"]
    assert isinstance(body["emotional_styles"], list) and body["emotional_styles"]
    assert {"id", "label", "speed", "pitch_semitones"} <= set(body["emotional_styles"][0])
