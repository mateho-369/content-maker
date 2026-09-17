"""Backgrounds: the choice has to reach the pixels, not just the settings row.

Before this feature existed the Director had no backdrop control at all; the risk
of adding one is a picker that stores a value nothing reads. So every test here ends
at something measurable:

* the catalog the picker renders *is* the catalog the renderer implements (one
  source, `ai_studio/backgrounds.py`);
* a value that cannot be painted is refused with the list of what is allowed, and a
  plate file that has gone missing is reported as `missing` rather than quietly
  replaced by the default;
* `settings.background` / `scene.meta.background` decide what is painted behind the
  subject **on the assembled cut** — measured on decoded frames of the final MP4;
* the caption band is checked against the plate, because white subtitles on a
  white studio is how captions "disappear" without anything failing.

Run: PYTHONPATH=. pytest tests/test_studio_backgrounds.py -q
"""
import os
import subprocess

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from ai_studio import backgrounds as bg
from ai_studio import config as cfg_mod
from ai_studio.app import StudioState, create_app
from ai_studio.qa import check_caption_contrast

LINE = "តើអ្នកធ្លាប់ស្រលាញ់មនុស្សម្នាក់? បាទ/ចាស។"


def ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


# ─────────────────────────────────────────────────────────── the value contract
@pytest.mark.parametrize("raw,kind,label", [
    (None, None, "auto (scene palette)"),
    ("white_studio", "studio", "White Studio"),
    ({"type": "black_studio"}, "studio", "Black Studio"),
    ({"type": "gradient", "a": "#101627", "b": "#2b3a63"}, "gradient", None),
    ({"type": "template", "template": "neon"}, "template", None),
    ({"type": "image", "path": "backgrounds/nope.png"}, "missing", None),
])
def test_every_background_the_ui_can_send_resolves(raw, kind, label):
    val = bg.normalize(raw)
    ok, err = bg.validate(val)
    assert ok, err
    res = bg.resolve(val, width=180, height=320)
    if kind is None:                                     # "no choice" really means none
        assert res is None
        assert bg.paint(res) is None and bg.plate(res, 180, 320) is None
    else:
        assert res["kind"] == kind, res
        assert res["w"] == 180 and res["h"] == 320, res
    if label:
        assert bg.label(raw) == label


def test_the_catalog_is_what_the_picker_renders():
    cat = bg.catalog()
    assert [t["key"] for t in cat["types"]] == list(bg.KINDS)
    assert cat["default"] == {"type": "white_studio"}
    for t in cat["types"]:
        assert t["default"]["type"] == t["key"]
        ok, why = bg.validate(t["default"])
        if ok:
            assert "needs" not in t, t          # nothing to complain about
        else:
            # an incomplete type (Custom Image, AI Generate) may exist, but it must
            # carry exactly the message the API answers with
            assert t.get("needs") == str(why), t
        for f in t.get("fields") or []:
            assert f["kind"] in ("color", "text", "number", "upload", "choice"), f
    # every declared input of every type is something the picker knows how to draw
    assert {f["kind"] for t in cat["types"] for f in (t.get("fields") or [])} <= \
        {"color", "text", "number", "upload", "choice"}
    # the caption warning travels with the type, so the picker can warn before a run
    assert "light plate" in next(t for t in cat["types"] if t["key"] == "white_studio")["note"]
    assert "white captions" in next(t for t in cat["types"] if t["key"] == "black_studio")["note"]


def test_an_unusable_background_is_named_not_substituted():
    ok, err = bg.validate({"type": "vhs_tunnel"})
    assert not ok
    assert "vhs_tunnel" in err and "white_studio" in err and "clear the cell" in err
    # a colour the picker could not parse falls back to the catalog default instead
    # of failing the run — and that default is what gets stored, not a lie
    ok, val = bg.validate({"type": "gradient", "a": "not-a-colour", "b": "#222222"})
    assert ok and val["a"] == "#0b1d3a" and val["b"] == "#222222"
    # a stored plate whose file is gone says so
    res = bg.resolve({"type": "image", "path": "backgrounds/gone.png"}, width=64, height=64)
    assert res["kind"] == "missing" and bg.plate(res, 64, 64) is None


def test_the_plate_changes_the_pixels():
    white = bg.plate(bg.resolve(bg.normalize("white_studio"), width=120, height=200), 120, 200)
    black = bg.plate(bg.resolve(bg.normalize("black_studio"), width=120, height=200), 120, 200)
    assert white.shape == black.shape == (200, 120, 3)
    assert float(white.mean()) > 168 and float(black.mean()) < 60
    assert "light plate" in bg.contrast_note(bg.normalize("white_studio"))
    assert bg.contrast_note({"type": "gradient", "a": "#808080", "b": "#808080"}) == ""


def test_preview_png_is_a_png_for_every_paintable_type():
    for t in bg.catalog()["types"]:
        if t["key"] in ("image", "ai_prompt"):
            continue                      # needs a file on disk / the image engine
        blob = bg.preview_png(t["default"], width=96, height=120)
        assert blob[:8] == b"\x89PNG\r\n\x1a\n", t["key"]
        assert len(blob) > 400, t["key"]


# ────────────────────────────────────────────────────────────────── the API
@pytest.fixture()
def studio(tmp_path):
    root = str(tmp_path)
    cfg = cfg_mod.load(os.path.join(root, "settings.json"))
    cfg["video"].update({"engine": "previz", "width": 256, "height": 448, "fps": 12,
                         "max_frames": 17, "min_frames": 14})
    cfg["tts"].update({"engine": "placeholder"})
    cfg["sfx"].update({"engine": "procedural"})
    cfg["rvc"].update({"enabled": False})
    cfg["assembly"].update({"fps": 12})
    cfg["pipeline"].update({"review_gate": False, "require_qa_pass": False, "max_scenes": 3})
    cfg_mod.save(cfg, os.path.join(root, "settings.json"))
    client = TestClient(create_app(root))
    with client:
        yield client, StudioState(root), root


def _project(st, settings=None):
    return st.db.create_project(title="bg", mode="A", status="ready",
                                script="\n".join([LINE] * 3),
                                settings={"control_mode": "manual", **(settings or {})})["id"]


def test_background_endpoints(studio, tmp_path):
    client, st, root = studio
    pid = _project(st)
    r0 = client.post(f"/api/projects/{pid}/scenes", json={"scenes": [
        {"text": LINE, "visual_prompt": "", "mood_tag": "calm",
         "estimated_duration_sec": 2.0, "audio_duration": 0, "sfx_prompt": "", "meta": {}},
        {"text": LINE, "visual_prompt": "", "mood_tag": "calm",
         "estimated_duration_sec": 2.0, "audio_duration": 0, "sfx_prompt": "",
         "meta": {"background": "black_studio"}},
        {"text": LINE, "visual_prompt": "", "mood_tag": "calm",
         "estimated_duration_sec": 2.0, "audio_duration": 0, "sfx_prompt": "", "meta": {}},
    ]})
    assert r0.status_code == 200, r0.text
    r = client.get("/api/backgrounds", params={"project_id": pid})
    assert r.status_code == 200, r.text
    cat = r.json()
    assert len(cat["types"]) == len(bg.KINDS) and cat["default"]["type"] == "white_studio"
    assert [sc["idx"] for sc in cat["scenes"]] == list(range(3))
    assert [sc["override"] for sc in cat["scenes"]] == [False, True, False], cat["scenes"]
    assert cat["scenes"][1]["background"]["type"] == "black_studio", cat["scenes"][1]

    png = client.get("/api/backgrounds/preview",
                     params={"type": "gradient", "a": "#000000", "b": "#000000",
                             "width": 96, "height": 96})
    assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert float(np.asarray(Image.open(__import__("io").BytesIO(png.content)).convert("L")).mean()) < 12
    bad = client.get("/api/backgrounds/preview", params={"type": "vhs_tunnel"})
    assert bad.status_code == 400 and "vhs_tunnel" in bad.text

    # uploads: only a real image, stored relative to the data dir so a project can
    # move machines and still find its plate
    txt = client.post("/api/backgrounds/upload", files={"file": ("plate.txt", b"not an image")})
    assert txt.status_code == 400 and "PNG" in txt.text, txt.text
    src = tmp_path / "plate.png"
    Image.new("RGB", (400, 700), (255, 0, 0)).save(src)
    with open(src, "rb") as fh:
        up = client.post("/api/backgrounds/upload", files={"file": ("plate.png", fh, "image/png")})
    assert up.status_code == 200, up.text
    val = up.json()["background"]
    assert val == {"type": "image", "path": val["path"]} and not os.path.isabs(val["path"])
    stored = os.path.join(root, val["path"])
    assert os.path.exists(stored)
    res = bg.resolve(val, width=180, height=320, data_root=root)
    assert res["kind"] == "plate", res          # "plate" = a file the renderer can read
    frame = bg.plate(res, 180, 320)
    assert frame is not None and float(frame[..., 0].mean()) > float(frame[..., 2].mean())

    # and the stored value round-trips through the project settings
    patch = client.patch(f"/api/projects/{pid}", json={"settings": {"background": val}})
    assert patch.status_code == 200, patch.text
    back = client.get("/api/backgrounds", params={"project_id": pid}).json()
    assert back["project"] == val, back["project"]
    # A half-configured background is refused at the door, not stored as a decision…
    bad = client.patch(f"/api/projects/{pid}", json={"settings": {"background": {"type": "ai_prompt"}}})
    assert bad.status_code == 400 and "prompt" in bad.text, bad.text
    # …while settings deep-merge, so re-picking a type keeps what was already filled
    # in for it (this is the "switch back to my last plate" case, not a hole)
    again = client.patch(f"/api/projects/{pid}", json={"settings": {"background": {"type": "image"}}})
    assert again.status_code == 200, again.text
    assert again.json()["project"]["settings"]["background"]["path"] == val["path"]
    assert client.patch(f"/api/projects/{pid}",
                        json={"settings": {"background": {}}}).status_code == 200


def test_project_background_and_a_scene_override_reach_the_cut(studio):
    client, st, root = studio
    pid = _project(st, settings={"background": {"type": "white_studio"}})
    r = client.post(f"/api/projects/{pid}/scenes", json={"scenes": [
        {"text": LINE, "visual_prompt": "", "mood_tag": "calm",
         "estimated_duration_sec": 2.0, "audio_duration": 0, "sfx_prompt": "", "meta": {}},
        {"text": LINE, "visual_prompt": "", "mood_tag": "calm",
         "estimated_duration_sec": 2.0, "audio_duration": 0, "sfx_prompt": "",
         "meta": {"background": "black_studio"}},
        {"text": LINE, "visual_prompt": "", "mood_tag": "calm",
         "estimated_duration_sec": 2.0, "audio_duration": 0, "sfx_prompt": "", "meta": {}},
    ]})
    assert r.status_code == 200, r.text
    out = client.post(f"/api/projects/{pid}/runs", json={"skip_stages": ["sfx", "qa"]}).json()
    status = None
    for _ in range(160):
        status = client.get(f"/api/runs/{out['run_id']}/status").json()
        if status["run"]["status"] in ("completed", "partial", "failed", "cancelled"):
            break
        import time
        time.sleep(0.5)
    run = status["run"]
    assert run["status"] == "completed", run.get("error") or status["stages"]

    # the clip metadata records which plate was painted, per scene
    vids = {a["scene_idx"]: a for a in status["assets"] if a["kind"] == "video"}
    assert vids, [a["kind"] for a in status["assets"]]
    assert vids[1]["meta"].get("background") == "black_studio", vids[1]["meta"]
    assert vids[0]["meta"].get("background") == "white_studio", vids[0]["meta"]

    final = [a for a in status["assets"] if a["kind"] == "final"]
    assert final, "a finished run must leave an MP4 behind"
    dur = float(final[0]["duration"])
    per = dur / 3.0

    def mean_at(t):
        probe = os.path.join(root, "probe.png")
        subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-ss", f"{t:.2f}",
                        "-i", final[0]["path"], "-frames:v", "1", probe], check=True)
        return float(np.asarray(Image.open(probe).convert("RGB")).mean())

    # the scene that asked for black really is dark on the finished cut, and its
    # neighbours kept the project's white plate (particles + captions lift both)
    bright, dark, bright2 = mean_at(per * 0.5), mean_at(per * 1.5), mean_at(per * 2.5)
    assert dark < 120 < 160 < bright, (bright, dark)
    assert bright2 > 160, bright2
    assert bright - dark > 80, (bright, dark)
    assert abs(bright - bright2) < 60, (bright, bright2)


def test_caption_contrast_check_is_measured_not_assumed(studio, tmp_path):
    for name, color in (("white", "white"), ("black", "black")):
        dst = str(tmp_path / f"{name}.mp4")
        subprocess.run([ffmpeg(), "-y", "-loglevel", "error",
                        "-f", "lavfi", "-i", f"color={color}:s=180x320:d=1.2",
                        "-f", "lavfi", "-i", "sine=frequency=200:duration=1.2",
                        "-pix_fmt", "yuv420p", "-shortest", "-c:a", "aac", dst], check=True)
        assert os.path.exists(dst)
    w = check_caption_contrast(str(tmp_path / "white.mp4"))
    b = check_caption_contrast(str(tmp_path / "black.mp4"))
    assert w["checked"] and b["checked"], (w, b)
    assert w["max_band_mean"] > 200 and not w["passed"], w        # near-white band → warn
    assert any(i["check"] == "caption_contrast" for i in w["issues"]), w
    assert b["max_band_mean"] < 60 and b["passed"] and not b["issues"], b
    gone = check_caption_contrast("")
    assert not gone["passed"] and "no final MP4" in gone["issues"][0]["issue"]
    # an unreadable file is a warning, never a silent pass
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"not a video at all")
    res = check_caption_contrast(str(junk))
    assert not res["checked"] and res["issues"][0]["severity"] == "warn", res
