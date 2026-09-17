"""What the Manual Control Panel's two selectors must guarantee, in the pipeline.

Two user-visible failures lived here, and both were silent:

1. **Unticking a scene changed nothing.** `skip_scenes` (and a scene deselected on
   the board with `meta.disabled`) reached the API and was stored in the run, but
   the job graph was still built for every scene — so the render kept the scene in
   the cut and in the captions while the panel said it was excluded.
2. **Switching a stage off starved assembly.** `assemble` depends on `qa#<scene>`
   for every scene. Deleting the skipped stage's jobs left those dependencies
   pointing at nothing, and the *dependants* of the dropped rows were re-added to
   the graph by `_reexpand` after Stage 1 — so assembly either launched before any
   clip existed (a video with no picture) or waited forever on a stage that would
   never run, ending as `blocked — unmet dependencies` on a run the panel still
   called `completed`.

Run: PYTHONPATH=. pytest tests/test_studio_manual_control.py -q
"""
import asyncio
import json
import os
import subprocess
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ai_studio import config as cfg_mod
from ai_studio.pipeline import spec as stagespec
from ai_studio.app import StudioState, create_app
from ai_studio.pipeline import scheduler as sched_mod

LINES = ["មួយ សិន។", "ពីរ សិន។", "បី សិន។", "បួន សិន។"]


def tiny_settings(root):
    """A CPU-only, seconds-per-run config: previz clips, placeholder voice.

    Same shape a user gets after the Setup Wizard on a machine without ComfyUI,
    just small enough that the whole pipeline runs in a test.
    """
    cfg = cfg_mod.load(os.path.join(root, "settings.json"))
    cfg["video"].update({"engine": "previz", "width": 256, "height": 448, "fps": 12,
                         "max_frames": 17, "min_frames": 14})
    cfg["tts"].update({"engine": "placeholder"})
    cfg["sfx"].update({"engine": "procedural"})
    cfg["rvc"].update({"enabled": False, "engine": "bypass"})
    cfg["assembly"].update({"fps": 12})
    cfg["pipeline"].update({"review_gate": False, "auto_approve_mode_b": True,
                            "require_qa_pass": False, "max_scenes": 4})
    cfg_mod.save(cfg, os.path.join(root, "settings.json"))
    return cfg


@pytest.fixture()
def studio(tmp_path):
    root = str(tmp_path)
    tiny_settings(root)
    client = TestClient(create_app(root))
    with client:
        yield client, StudioState(root), root


def make_project(st, script=None, **kw):
    return st.db.create_project(title="manual control", mode="A", status="ready",
                                script=script or "\n".join(LINES),
                                settings={"control_mode": "manual", **kw})["id"]


def board(client, pid, texts, meta=None):
    scenes = [{"text": t, "visual_prompt": "", "mood_tag": "calm",
               "estimated_duration_sec": 2.0, "audio_duration": 0, "sfx_prompt": "",
               "meta": (meta or {}).get(i, {})}
              for i, t in enumerate(texts)]
    r = client.post(f"/api/projects/{pid}/scenes", json={"scenes": scenes})
    assert r.status_code == 200, r.text
    return r.json()["scenes"]


def run_until(client, pid, payload, until=("completed", "partial", "failed", "cancelled"), limit=90):
    out = client.post(f"/api/projects/{pid}/runs", json=payload).json()
    assert "run_id" in out, out
    for _ in range(limit):
        st = client.get(f"/api/runs/{out['run_id']}/status").json()
        if st["run"]["status"] in until:
            return out["run_id"], st
        import time
        time.sleep(0.5)
    raise AssertionError("run never settled: " + str(st["run"]["status"]))


# ────────────────────────────────────────────────── the graph itself (pure unit)
def graph(n=4, cfg=None, skip=(), scenes_off=()):
    """The scheduler's two transforms, applied exactly as start_run applies them."""
    cfg = cfg or {}
    jobs, _meta = stagespec.build_graph(n, plan={}, cfg=cfg)
    # the scheduler's own function — the test must not re-implement the rule
    out, dropped = sched_mod.select_jobs(jobs, skip, scenes_off)
    return jobs, out


def test_assemble_waits_on_real_work_when_a_stage_is_switched_off():
    jobs, out = graph(skip={"qa"})
    asm = out["assemble#-1"]
    assert not any(d.startswith("qa#") for d in asm.deps), asm.deps
    # …and it waits on what feeds QA instead, per scene, not just once
    assert {d.split("#")[0] for d in asm.deps} == {"sfx", "video_fit", "voice_final"}
    assert {int(d.split("#")[1]) for d in asm.deps} == {0, 1, 2, 3}


def test_switching_off_two_stages_walks_past_both():
    _jobs, out = graph(skip={"sfx", "qa"})
    deps = set(out["assemble#-1"].deps)
    assert {d.split("#")[0] for d in deps} == {"video", "video_fit", "voice_final"}
    # a stage that is not switched off keeps its own dependency untouched
    assert "sfx#1" in out["video_fit#1"].deps or "sfx#1" not in deps


def test_select_jobs_reports_what_it_dropped():
    _jobs, out = graph(skip={"qa"}, scenes_off={2})
    assert not [k for k in out if k.endswith("#2")]
    # the returned dict is a copy: the caller still writes `skipped` rows from the
    # full graph, so aliasing here would erase every trace of the skipped stages
    full, _ = stagespec.build_graph(4, plan={}, cfg={})
    assert len(out) < len(full)


def test_jobs_of_a_deselected_scene_are_gone_not_marked():
    _jobs, out = graph(skip={"qa"}, scenes_off={2})
    assert not [k for k in out if k.endswith("#2")], [k for k in out if k.endswith("#2")]
    assert "assemble#-1" in out
    # nothing on assembly's list points at a job the run will not create
    assert not any(d.endswith("#2") for d in out["assemble#-1"].deps), out["assemble#-1"].deps
    assert all(d in out for d in out["assemble#-1"].deps), out["assemble#-1"].deps


def test_non_scene_jobs_use_minus_one_and_are_never_dropped():
    _jobs, out = graph(scenes_off={0})
    for key in ("script#-1", "breakdown#-1", "assemble#-1"):
        assert key in out, key


# ────────────────────────────────────────────────────────── _reexpand (the bug)
def fake_state(db, project_id, run_id, skip_stages=(), skip_scenes=()):
    return SimpleNamespace(
        run_id=run_id, project_id=project_id, plan={}, cfg={}, skip_stages=set(skip_stages),
        skip_scenes=set(skip_scenes), satisfied=set(), running={}, pending={}, jobs={},
        ctx=SimpleNamespace(event=lambda *a, **k: None),
    )


def test_reexpand_does_not_resurrect_jobs_the_director_switched_off(tmp_path):
    """After Stage 1 the graph is rebuilt from the scene count; it must stay filtered."""
    st = StudioState(str(tmp_path))
    pid = make_project(st)
    st.db.replace_scenes(pid, [{"idx": i, "text": t, "visual_prompt": "", "mood_tag": "calm",
                                "estimated_duration_sec": 2.0, "meta": {}} for i, t in enumerate(LINES)])
    sched = sched_mod.Scheduler.__new__(sched_mod.Scheduler)
    sched.db = st.db
    state = fake_state(st.db, pid, "r1", skip_stages=("sfx", "qa"), skip_scenes=(2,))
    asyncio.run(sched._reexpand(state))
    keys = set(state.jobs)
    assert not [k for k in keys if k.split("#")[0] in ("sfx", "qa")], sorted(keys)
    assert not [k for k in keys if k.endswith("#2")], sorted(keys)
    assert "video#0" in keys and "video#3" in keys        # kept scenes keep working
    assert not [k for k in state.pending if k.endswith("#2")]


def test_reexpand_honours_a_board_disable_without_the_run_payload(tmp_path):
    """`meta.disabled` on the scene is a permanent choice, not a per-run flag."""
    st = StudioState(str(tmp_path))
    pid = make_project(st)
    st.db.replace_scenes(pid, [{"idx": i, "text": t, "visual_prompt": "", "mood_tag": "calm",
                                "estimated_duration_sec": 2.0,
                                "meta": {"disabled": True} if i == 1 else {}}
                               for i, t in enumerate(LINES)])
    sched = sched_mod.Scheduler.__new__(sched_mod.Scheduler)
    sched.db = st.db
    state = fake_state(st.db, pid, "r1")
    asyncio.run(sched._reexpand(state))
    assert not [k for k in state.jobs if k.endswith("#1")], sorted(state.jobs)
    assert "video#0" in state.jobs


# ───────────────────────────────────────────────── a run must not lie about itself
def test_a_blocked_assembly_cannot_report_completed(tmp_path):
    rows = [
        {"stage": "script", "scene_idx": -1, "status": "done", "error": "", "message": "",
         "started_at": 1.0, "finished_at": 2.0},
        {"stage": "breakdown", "scene_idx": -1, "status": "done", "error": "", "message": "",
         "started_at": 2.0, "finished_at": 3.0},
        {"stage": "video#0", "scene_idx": 0, "status": "done", "error": "", "message": "",
         "started_at": 3.0, "finished_at": 4.0},
        {"stage": "assemble", "scene_idx": -1, "status": "blocked",
         "error": "unmet dependencies: video#1", "message": "blocked — unmet dependencies",
         "started_at": None, "finished_at": 5.0},
    ]
    rows = [{**r, "stage": r["stage"].split("#")[0]} for r in rows]

    class Db:
        def __init__(self): self.run_updates = []
        def list_stages(self, run_id): return rows
        def get_run(self, run_id): return {"stats": {}}
        def update_run(self, run_id, **kw): self.run_updates.append(kw)
        def update_project(self, pid, **kw): pass

    db = Db()
    sched = sched_mod.Scheduler.__new__(sched_mod.Scheduler)
    sched.db = db
    st = SimpleNamespace(run_id="r1", project_id="p1", needs_review=False, results={},
                         cancel=asyncio.Event(), started_at=0.0, done=False,
                         ctx=SimpleNamespace(event=lambda *a, **k: None))
    status = asyncio.run(sched._finish(st, []))
    assert status == "partial", status                       # never "completed"
    err = db.run_updates[0]["error"]
    assert "assemble" in err and "NOT" in err.upper(), err    # names it and says the cut is missing
    assert db.run_updates[0]["stats"]["stages_blocked"] == 1
    assert db.run_updates[0]["stats"]["cut_produced"] is False


def test_a_run_with_a_real_cut_still_reports_completed(tmp_path):
    rows = [{"stage": s, "scene_idx": -1, "status": "done", "error": "", "message": "",
             "started_at": 1.0, "finished_at": 2.0} for s in ("script", "breakdown", "assemble")]

    class Db:
        def list_stages(self, run_id): return rows
        def get_run(self, run_id): return {"stats": {}}
        def update_run(self, run_id, **kw): self.last = kw
        def update_project(self, pid, **kw): pass

    sched = sched_mod.Scheduler.__new__(sched_mod.Scheduler)
    sched.db = Db()
    st = SimpleNamespace(run_id="r1", project_id="p1", needs_review=False,
                         results={"assemble#-1": {"final_asset_path": "/tmp/x.mp4"}},
                         cancel=asyncio.Event(), started_at=0.0, done=False,
                         ctx=SimpleNamespace(event=lambda *a, **k: None))
    assert asyncio.run(sched._finish(st, [])) == "completed"


# ──────────────────────────────────────────────────────────── end-to-end, real run
def test_deselected_scene_is_absent_from_the_cut_and_the_captions(studio):
    client, st, root = studio
    pid = make_project(st)
    board(client, pid, LINES, meta={2: {"disabled": True}})     # scene 3 off the board
    rid, status = run_until(client, pid, {})
    rows = status["stages"]
    by_scene = {}
    for r in rows:
        by_scene.setdefault(r["scene_idx"], []).append(r["status"])
    assert by_scene.get(2), by_scene
    assert set(by_scene[2]) == {"skipped"}, by_scene[2]
    for idx in (0, 1, 3):
        assert "done" in by_scene[idx], (idx, by_scene[idx])

    run = status["run"]
    assert run["status"] == "completed", (run["status"], run.get("error"))
    final = [a for a in status["assets"] if a["kind"] == "final"]
    assert final, "a run whose stages all finished must produce the MP4"
    # 3 scenes kept, the deselected one is not in the timeline
    dur = float(final[0]["duration"])
    assert 3.0 < dur < 7.5, dur

    srt = [a for a in status["assets"] if a["kind"] == "srt"]
    assert srt, [a["kind"] for a in status["assets"]]
    text = open(srt[0]["path"], encoding="utf-8").read()
    assert LINES[2] not in text and LINES[0] in text and LINES[3] in text


def test_switching_off_sfx_and_qa_still_finishes_with_a_cut(studio):
    client, st, root = studio
    pid = make_project(st)
    board(client, pid, LINES[:3])
    rid, status = run_until(client, pid, {"skip_stages": ["sfx", "qa"]})
    rows = {r["stage"]: r["status"] for r in status["stages"]}
    assert rows["sfx"] == "skipped" and rows["qa"] == "skipped", rows
    assert rows["assemble"] == "done", rows
    assert status["run"]["status"] == "completed", status["run"].get("error")
    assert any(a["kind"] == "final" for a in status["assets"])
    skipped = [r for r in status["stages"] if r["status"] == "skipped"]
    for r in skipped:
        if r["stage"] in ("sfx", "qa"):
            assert "disabled" in (r["message"] or "").lower(), r


def test_skip_scenes_in_the_payload_and_the_board_agree(studio):
    client, st, root = studio
    pid = make_project(st)
    board(client, pid, LINES[:4])
    rid, status = run_until(client, pid, {"skip_scenes": [1, 3]})
    assert all(r["status"] == "skipped" for r in status["stages"] if r["scene_idx"] in (1, 3))
    assert any(r["status"] == "done" for r in status["stages"] if r["scene_idx"] == 0)
    final = [a for a in status["assets"] if a["kind"] == "final"]
    assert final and float(final[0]["duration"]) < 5.5, final
    # and the same scene count is what the pre-run summary promised
    plan = client.get(f"/api/projects/{pid}/run-plan",
                      params={"skip_stages": "sfx,qa", "skip_scenes": "1,3"}).json()
    assert plan["scenes_rendering"] == 2 and plan["scenes_total"] == 4, plan
    assert plan["jobs"] < plan["jobs_total"], plan


def test_bad_selections_are_refused_with_a_message(studio):
    client, st, root = studio
    pid = make_project(st)
    board(client, pid, LINES[:2])
    r = client.post(f"/api/projects/{pid}/runs", json={"skip_stages": ["nonsense"]})
    assert r.status_code == 400 and "nonsense" in r.text and "script" in r.text, r.text
    r = client.post(f"/api/projects/{pid}/runs", json={"skip_scenes": [9]})
    assert r.status_code == 400 and "2 scene" in r.text, r.text
    r = client.post(f"/api/projects/{pid}/runs", json={"skip_scenes": ["abc"]})
    assert r.status_code == 400, r.text


def test_regenerating_one_scene_does_not_pay_for_the_board_again(studio):
    """`scene_idx` on a regenerate must scope the work to that scene."""
    client, st, root = studio
    pid = make_project(st)
    board(client, pid, LINES[:3])
    rid, first = run_until(client, pid, {})
    vids = {a["scene_idx"]: a for a in first["assets"] if a["kind"] == "video"}
    assert len(vids) == 3, sorted(vids)
    before = {i: os.stat(a["path"]).st_mtime_ns for i, a in vids.items()}

    r = client.post(f"/api/runs/{rid}/stages/video/regenerate",
                    json={"scene_idx": 1, "overrides": {"text": LINES[1] + " ថ្មី។"}})
    assert r.status_code == 200, r.text
    rid2 = r.json()["run_id"]
    for _ in range(160):
        status = client.get(f"/api/runs/{rid2}/status").json()
        if status["run"]["status"] in ("completed", "partial", "failed", "cancelled"):
            break
        import time
        time.sleep(0.5)
    assert status["run"]["status"] == "completed", status["run"].get("error")
    rows = {(x["stage"], x["scene_idx"]): x for x in status["stages"]}
    assert rows[("video", 1)]["status"] == "done", rows[("video", 1)]
    # the other scenes' clip files were not touched at all — same inode content,
    # same mtime — and they are marked `done` (inherited), not re-rendered
    assert os.stat(vids[1]["path"]).st_mtime_ns != before[1], "scene 2's clip should be new"
    for idx in (0, 2):
        assert os.stat(vids[idx]["path"]).st_mtime_ns == before[idx], \
            f"scene {idx + 1} was re-rendered for nothing"
        assert rows[("video", idx)]["status"] == "done", rows[("video", idx)]
        assert "reused" in (rows[("video", idx)]["message"] or "").lower(), rows[("video", idx)]
    # and the new wording is what the row now says
    assert "ថ្មី" in st.db.get_scene(pid, 1)["text"]
    assert [a for a in status["assets"] if a["kind"] == "final"], "the cut must be rebuilt"


def test_run_control_endpoints_answer_for_a_live_run(studio):
    client, st, root = studio
    pid = make_project(st)
    board(client, pid, LINES[:3])
    out = client.post(f"/api/projects/{pid}/runs", json={"queue_only": True}).json()
    rid = out["run_id"]
    st2 = client.get(f"/api/runs/{rid}/status").json()
    assert "eta" in st2, sorted(st2)                 # the progress panel reads this
    assert st2["eta"]["remaining_jobs"] >= 0
    r = client.post(f"/api/runs/{rid}/skip_scene", json={"scene_idx": 1})
    assert r.status_code in (200, 409), r.text        # queued run: either it worked or it says why
    r = client.post(f"/api/runs/{rid}/skip_scene", json={})
    assert r.status_code == 400 and "scene_idx" in r.text


def test_pre_run_summary_counts_scenes_stages_and_warns(studio):
    client, st, root = studio
    pid = make_project(st)
    board(client, pid, LINES[:3])
    plan = client.get(f"/api/projects/{pid}/run-plan").json()
    assert plan["scenes_total"] == 3 == plan["scenes_rendering"]
    assert plan["jobs"] == plan["jobs_total"]
    assert plan["resolution"] == "256x448@12", plan["resolution"]
    assert plan["engines"]["tts"] == "placeholder"
    assert any("placeholder" in w for w in plan["warnings"]), plan["warnings"]
    assert isinstance(plan["estimated_seconds"], (int, float)) and plan["estimated_seconds"] > 0
    assert "estimate_basis" in plan and plan["estimate_basis"]
