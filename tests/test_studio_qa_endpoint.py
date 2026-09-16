"""`GET /api/qa/project/{id}` — the QA Gate the project page runs on mount.

Three things this endpoint got wrong, all of them visible from the UI:

* a project that exists but has no scenes answered **404 "Project or scenes
  not found"**. Opening any draft project therefore threw a red error toast at
  the browser console (`api.ts:51 GET /api/qa/project/p… 404`), and a genuinely
  missing project was indistinguishable from an untouched draft;
* `st.final_video(project_id) if hasattr(st, "final_video")` guarded a method
  `StudioState` never had, so the "final MP4 container" check *never ran*: the
  gate printed "APPROVED FOR EXPORT" without ever looking at the export;
* `/api/tts/providers-and-styles` read `st.cfg` (also not an attribute of
  StudioState), so it 500'd on every call.

Run: PYTHONPATH=. pytest tests/test_studio_qa_endpoint.py -q
"""
import os

import pytest
from fastapi.testclient import TestClient

from ai_studio.app import StudioState, create_app

LINE = "ជីវិតមនុស្ស មិនមែនជាប្រណាំងទេ។ វាគឺជាដំណើរ។"


@pytest.fixture()
def studio(tmp_path):
    st = StudioState(str(tmp_path))
    client = TestClient(create_app(str(tmp_path)))
    return st, client


def _scene_project(st, **kw):
    pid = st.db.create_project(title="qa", mode="A", status="ready",
                               script=LINE, **kw)["id"]
    st.db.replace_scenes(pid, [{"text": LINE, "visual_prompt": "a quiet field",
                                "mood_tag": "calm-warm", "estimated_duration_sec": 5.0}] * 3)
    return pid


def test_draft_project_with_no_scenes_is_pending_not_404(studio):
    st, client = studio
    pid = st.db.create_project(title="untouched", mode="A", status="draft")["id"]
    r = client.get(f"/api/qa/project/{pid}")
    assert r.status_code == 200, r.text
    d = r.json()
    # the panel reads these unguarded: a missing array used to crash the view
    assert d["pending"] is True and d["approved"] is False
    assert d["failures"] == [] and d["fail_count"] == 0
    assert isinstance(d["warnings"], list) and d["warnings"]
    assert d["total_scenes"] == 0


def test_unknown_project_is_a_404_with_an_honest_detail(studio):
    _st, client = studio
    r = client.get("/api/qa/project/pnope")
    assert r.status_code == 404
    assert r.json()["detail"] == "project not found"


def test_the_gate_actually_opens_the_rendered_mp4(studio):
    """A 1 KB 'final' asset is not a video — the gate must say so.

    Before `StudioState.final_video()` existed this returned approved=True with
    zero failures, because the container check was skipped by `hasattr`.
    """
    st, client = studio
    pid = _scene_project(st)
    final_dir = os.path.join(st.data_root, "projects", pid, "final")
    os.makedirs(final_dir, exist_ok=True)
    bogus = os.path.join(final_dir, "run1.mp4")
    with open(bogus, "wb") as f:
        f.write(b"\x00" * 1024)
    st.db.add_asset(pid, "final", bogus, stage="assemble", scene_idx=-1)

    d = client.get(f"/api/qa/project/{pid}").json()
    assert d["final_mp4"] == bogus and d["mp4_checked"] is True
    assert d["mp4_verified"] is False
    assert any(f["check"] == "mp4" for f in d["failures"]), d["failures"]
    assert d["approved"] is False


def test_a_render_recorded_but_missing_from_disk_fails(studio):
    """Deleting the export must not turn the gate green by omission."""
    st, client = studio
    pid = _scene_project(st)
    ghost = os.path.join(st.data_root, "projects", pid, "final", "run9.mp4")
    st.db.add_asset(pid, "final", ghost, stage="assemble", scene_idx=-1)

    d = client.get(f"/api/qa/project/{pid}").json()
    assert d["mp4_checked"] is True and d["mp4_verified"] is False
    assert any("does not exist" in f["issue"] for f in d["failures"]), d["failures"]
    assert d["approved"] is False


def test_a_project_that_never_rendered_reports_no_export(studio):
    st, client = studio
    pid = _scene_project(st)
    d = client.get(f"/api/qa/project/{pid}").json()
    assert d["pending"] is False and d["final_mp4"] == ""
    assert d["mp4_checked"] is False and d["mp4_verified"] is False


def test_final_video_falls_back_to_the_run_stats(studio, tmp_path):
    """Runs written before the asset row landed still resolve their MP4."""
    st, _client = studio
    pid = _scene_project(st)
    path = str(tmp_path / "from_stats.mp4")
    run = st.db.create_run(pid)
    st.db.update_run(run["id"], stats={"final_path": path})
    assert st.final_video(pid) == path
    assert st.final_video("pnothing") == ""


def test_content_type_comes_from_the_project_column(studio):
    st, client = studio
    pid = _scene_project(st, content_type="compare")
    d = client.get(f"/api/qa/project/{pid}").json()
    assert d["content_type"] == "compare"


def test_tts_providers_and_styles_endpoint_responds(studio):
    """`st.cfg` raised AttributeError -> 500 on every call."""
    _st, client = studio
    r = client.get("/api/tts/providers-and-styles")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["providers"] and body["emotional_styles"]
    assert {"id", "label", "desc"} <= set(body["emotional_styles"][0])
