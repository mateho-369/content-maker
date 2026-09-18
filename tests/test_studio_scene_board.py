"""The manual workflow: what the Scene Board writes, the render must read.

The board's own save (`POST /api/projects/{id}/scenes`) was destroying the
Director's choices in three ways, all of them silent:

* `meta` was filtered to 4 keys, so action, prop, emotion_style and meme_type —
  the four pickers in the board — never reached the DB (and Stage 3a/4 read
  exactly those keys, so the render ignored what the board showed);
* `visual_source` was validated against a list that lacked `character_action`
  and `meme`, and anything unknown was rewritten to `generated_video` — which on
  machine_b means "defer to the GPU machine", so saving a board quietly
  re-planned the whole video onto a deferred stage;
* an all-empty board answered `400 "no usable scenes"`, which told a manual
  user nothing about what to do next.

Run: PYTHONPATH=. pytest tests/test_studio_scene_board.py -q
"""
import pytest
from fastapi.testclient import TestClient

from ai_studio import content as content_mod
from ai_studio.app import StudioState, create_app
from ai_studio.pipeline.fallbacks import deterministic_breakdown

LINE = "តើអ្នកធ្លាប់ស្រលាញ់មនុស្សម្នាក់ ដែលស្រលាញ់អ្នកវិញតែពេលគេត្រូវការអ្នកទេ?"


@pytest.fixture()
def board(tmp_path):
    """One studio + one project (with a character, since the board can point at
    character sources) sharing the same data dir."""
    st = StudioState(str(tmp_path))
    client = TestClient(create_app(str(tmp_path)))
    char = st.db.create_character(name="Ara")["id"]
    pid = st.db.create_project(title="board", mode="A", status="ready", script=LINE,
                               character_id=char,
                               settings={"control_mode": "manual"})["id"]
    return client, st, pid


def save(client, pid, scenes):
    return client.post(f"/api/projects/{pid}/scenes", json={"scenes": scenes})


def test_every_picker_key_survives_a_save(board):
    client, st, pid = board
    r = save(client, pid, [{"text": LINE, "visual_prompt": "a field", "mood_tag": "calm-warm",
                            "estimated_duration_sec": 6,
                            "meta": {"visual_source": "character_action", "render_mode": "broll",
                                     "character_action": "thinking", "prop": "phone",
                                     "emotion_style": "surprised", "meme_type": "meme_dramatic_zoom",
                                     "side": "A"}}])
    assert r.status_code == 200, r.text
    meta = st.db.list_scenes(pid)[0]["meta"]
    for key, want in [("character_action", "thinking"), ("prop", "phone"),
                      ("emotion_style", "surprised"), ("meme_type", "meme_dramatic_zoom"),
                      ("visual_source", "character_action"), ("side", "A")]:
        assert meta.get(key) == want, f"{key} was dropped on save: {meta}"


# The four options VisualSourceControl renders, spelled out here (not imported
# from the backend) so this test fails if the two lists ever disagree.
UI_VISUAL_SOURCES = ("character_action", "illustration", "meme", "generated_video")


def test_the_board_vocabulary_is_the_server_vocabulary():
    assert set(UI_VISUAL_SOURCES) <= set(content_mod.VISUAL_SOURCES), (
        f"the UI offers {set(UI_VISUAL_SOURCES) - set(content_mod.VISUAL_SOURCES)} that the "
        "studio refuses to save")


@pytest.mark.parametrize("source", UI_VISUAL_SOURCES)
def test_no_visual_source_the_ui_can_offer_is_rewritten(board, source):
    """`character_action` and `meme` used to be silently turned into generated_video."""
    client, st, pid = board
    r = save(client, pid, [{"text": LINE, "meta": {"visual_source": source}}])
    assert r.status_code == 200, r.text            # accepted as-is, whatever it is
    assert st.db.list_scenes(pid)[0]["meta"]["visual_source"] == source


def test_a_source_the_studio_cannot_render_is_refused_not_rewritten(board):
    client, _st, pid = board
    r = save(client, pid, [{"text": LINE, "meta": {"visual_source": "wide_shot_drones"}}])
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "wide_shot_drones" in detail and "scene 1" in detail
    assert "illustration" in detail          # names the accepted vocabulary


def test_an_unfinished_row_is_named_not_swallowed(board):
    """A blank row is a scene being written, not a deletion. Dropping it silently
    meant "+ add scene" + a save habit ate the rows the Director had just made."""
    client, st, pid = board
    r = save(client, pid, [{"text": LINE, "meta": {}}, {"text": "   ", "meta": {}}])
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "scene 2" in detail and "no narration" in detail and "✕" in detail
    # and the refusal is total: a partial save would strand the board
    assert st.db.list_scenes(pid) == []

    r = save(client, pid, [])
    assert r.status_code == 400
    assert "add scene" in r.json()["detail"] and "import script" in r.json()["detail"]

    r = save(client, pid, [{"text": ""}, {"text": " "}])
    assert r.status_code == 400 and "no narration" in r.json()["detail"]


def test_a_full_board_saves_and_reports_the_count(board):
    client, st, pid = board
    r = save(client, pid, [{"text": LINE, "meta": {}}, {"text": LINE, "meta": {}}])
    assert r.status_code == 200 and r.json()["note"].startswith("storyboard saved · 2 scene(s)")
    assert len(st.db.list_scenes(pid)) == 2


def test_talking_head_without_a_character_names_the_scene_and_the_fix(board):
    client, st, pid = board
    st.db.update_project(pid, character_id="")      # no character anywhere
    r = save(client, pid, [{"text": LINE, "meta": {"render_mode": "talking_head"}},
                           {"text": LINE, "meta": {}}])
    assert r.status_code == 400
    assert "scene 1" in r.json()["detail"] and "Characters" in r.json()["detail"]


def test_the_save_returns_the_stored_rows_so_the_ui_need_not_refetch(board):
    client, _st, pid = board
    body = save(client, pid, [{"text": LINE, "meta": {}}]).json()
    assert len(body["scenes"]) == 1 and body["scenes"][0]["idx"] == 0
    assert body["project"]["id"] == pid and "scenes" not in body["project"]
    assert "integrity" in body


def test_a_hand_authored_board_survives_a_run(tmp_path):
    """Re-running must not trim a manual board to max_scenes or filter its meta."""
    from ai_studio import config as cfg_mod

    cfg = cfg_mod.load(str(tmp_path / "settings.json"))
    cfg["pipeline"]["max_scenes"] = 3
    board = [{"text": LINE, "visual_prompt": "v", "mood_tag": "calm-warm",
              "estimated_duration_sec": 4.0,
              "meta": {"visual_source": "character_action", "character_action": "pointing",
                       "prop": "phone", "emotion_style": "happy"}}] * 5
    got = deterministic_breakdown(LINE * 5, cfg, plan_scenes=board, content_type="explainer")
    assert len(got) == 5, f"the board was truncated to {len(got)} scenes"
    for sc in got:
        m = sc["meta"]
        assert m["character_action"] == "pointing" and m["prop"] == "phone"
        assert m["emotion_style"] == "happy"
        assert m["visual_source"] == "character_action"


def test_auto_segmentation_still_respects_max_scenes(tmp_path):
    from ai_studio import config as cfg_mod

    cfg = cfg_mod.load(str(tmp_path / "settings.json"))
    cfg["pipeline"]["max_scenes"] = 2
    got = deterministic_breakdown("\n".join([LINE] * 6), cfg, plan_scenes=None,
                                  content_type="explainer")
    assert len(got) == 2


def test_repeated_saves_do_not_nest_meta(board):
    """The board echoes stored rows back; a redundant nested `meta` used to be kept
    forever by the flatten-one-level compensation in list_scenes."""
    client, st, pid = board
    payload = [{"text": LINE, "meta": {"visual_source": "meme"}}]
    for _ in range(3):
        saved = save(client, pid, payload).json()["scenes"]
        meta = saved[0]["meta"]
        assert "meta" not in meta, meta
        assert meta["visual_source"] == "meme"
        payload = [{"text": saved[0]["text"], "meta": meta}]


def test_a_non_numeric_duration_is_a_400_naming_the_field(board):
    client, _st, pid = board
    r = save(client, pid, [{"text": LINE, "estimated_duration_sec": "five seconds"}])
    assert r.status_code == 400 and "estimated_duration_sec" in r.json()["detail"]
    # "" (a cleared spinner) is a zero, not an error
    assert save(client, pid, [{"text": LINE, "estimated_duration_sec": ""}]).status_code == 200


def test_a_non_object_scene_or_meta_is_a_400_not_a_500(board):
    client, _st, pid = board
    assert save(client, pid, ["just a string"]).status_code == 400
    assert save(client, pid, [{"text": LINE, "meta": "meme"}]).status_code == 400
    assert save(client, pid, {"scenes": "nope"}).status_code == 400
