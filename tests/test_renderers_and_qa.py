"""Regression tests for the sample-production renderers and the QA gate.

Covers the failure that shipped silently for a while: the white-studio renderer
pointed its two "internet photo" scenes at filenames that were not in
image-search/, `create_white_background` skipped the missing files without a
word, and the console still printed `[Img: True]` while QA reported
`Approved: True`.
"""
import importlib
import os
import subprocess
import sys

import cv2
import numpy as np
import pytest

from ai_studio import app as app_mod
from ai_studio import qa

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARD_BOX = (60, 80, 660, 420)          # (x1, y1, x2, y2) of the floating photo card


@pytest.fixture(scope="module")
def renderer():
    sys.path.insert(0, REPO_ROOT)
    try:
        yield importlib.import_module("render_love_vs_situationship_white")
    finally:
        if REPO_ROOT in sys.path:
            sys.path.remove(REPO_ROOT)


def _card(frame):
    x1, y1, x2, y2 = CARD_BOX
    return frame[y1:y2, x1:x2]


# ------------------------------------------------------------------ the photos
def test_every_declared_example_photo_exists(renderer):
    """No scene may declare a photo the repo does not ship."""
    for scene in renderer.SCENES:
        if not scene.get("has_example_img"):
            continue
        path = scene["example_img"]
        assert path, f"scene {scene['idx']} declares a photo but has no path"
        assert os.path.isfile(path), f"scene {scene['idx']} photo missing: {path}"
        assert cv2.imread(path) is not None, f"scene {scene['idx']} photo unreadable: {path}"


def test_resolve_example_image_falls_back_to_the_next_candidate(renderer, capsys):
    wanted = "image-search/renamed-or-gone.jpg"
    fallback = os.path.join(REPO_ROOT, "image-search", "happy-couple-holding-hands-romantic-date-1.jpg")
    got = renderer.resolve_example_image(
        [wanted, "image-search/happy-couple-holding-hands-romantic-date-1.jpg"], "Real Love")
    assert os.path.normcase(got) == os.path.normcase(fallback)
    assert capsys.readouterr().out == "", "a resolved photo is not worth a warning"


def test_resolve_example_image_warns_when_nothing_is_on_disk(renderer, capsys):
    assert renderer.resolve_example_image(["image-search/renamed-or-gone.jpg"], "Situationship") is None
    out = capsys.readouterr().out
    assert "Example photo missing for Situationship" in out
    assert "image-search/renamed-or-gone.jpg" in out


def test_read_example_photo_rejects_missing_and_corrupt(renderer, tmp_path):
    assert renderer.read_example_photo(None) is None
    assert renderer.read_example_photo(str(tmp_path / "nope.jpg")) is None
    corrupt = tmp_path / "corrupt.jpg"
    corrupt.write_bytes(b"not a jpeg at all")
    assert renderer.read_example_photo(str(corrupt)) is None

    photo = renderer.IMG_REAL_LOVE
    assert renderer.read_example_photo(None, example_photo=cv2.imread(photo)) is not None


# ------------------------------------------------------------- the drawn card
def test_photo_card_is_actually_drawn(renderer):
    plain = renderer.create_white_background(720, 1280)
    with_photo = renderer.create_white_background(720, 1280, renderer.IMG_REAL_LOVE, "REAL LOVE")

    assert not np.array_equal(_card(plain), _card(with_photo)), \
        "the floating card looked identical with and without the photo"
    # the real photo is a photograph: far more colour variance than the white studio bg
    assert float(_card(with_photo).std()) > float(_card(plain).std())

    # a path that does not exist renders exactly like no photo at all
    assert np.array_equal(_card(plain),
                          _card(renderer.create_white_background(720, 1280, "image-search/missing-file.jpg")))


def test_photo_is_decoded_once_and_reused(renderer):
    photo = cv2.imread(renderer.IMG_SITUATIONSHIP)
    via_path = renderer.create_white_background(720, 1280, renderer.IMG_SITUATIONSHIP, "SITUATIONSHIP")
    via_frame = renderer.create_white_background(720, 1280, None, "SITUATIONSHIP", example_photo=photo)
    assert np.array_equal(via_path, via_frame)


def test_scene_image_note_reports_reality(renderer, tmp_path):
    assert renderer.scene_image_note({"example_img": None}) == "no"
    assert renderer.scene_image_note({"example_img": renderer.IMG_REAL_LOVE}) == "yes"
    note = renderer.scene_image_note({"example_img": str(tmp_path / "gone.jpg")})
    assert note.startswith("MISSING →"), note


# -------------------------------------------------------------------- QA gate
def _scene(text="តើអ្នកកំពុងមាន Real Love ឬ Situationship?", **extra):
    return {"idx": 0, "text": text, "estimated_duration_sec": 3.0, "audio_duration": 3.0, **extra}


def test_qa_gate_fails_when_a_declared_example_image_is_missing(tmp_path):
    scenes = [_scene(example_img=str(tmp_path / "does-not-exist.jpg"))]
    res = qa.run_full_project_qa(scenes, content_type="compare")
    assert res["approved"] is False
    checks = [i["check"] for i in res["failures"]]
    assert "example_asset" in checks
    assert res["failures"][0]["scene_idx"] == 0


def test_qa_gate_passes_when_the_example_image_exists():
    scenes = [_scene(example_img=os.path.join("image-search", "happy-couple-holding-hands-romantic-date-1.jpg"))]
    res = qa.run_full_project_qa(scenes, content_type="compare")
    assert "example_asset" not in [i["check"] for i in res["failures"] + res["warnings"]]


def test_qa_gate_uses_measured_audio_durations():
    long_hook = "តើអ្នកកំពុងមាន Real Love ឬគ្រាន់តែជា Situationship? " * 4   # > 80 chars
    scenes = [_scene(text=long_hook, audio_duration=12.0, estimated_duration_sec=12.0)]
    res = qa.run_full_project_qa(scenes, content_type="explainer")
    assert "hook_pacing" in [i["check"] for i in res["warnings"]], \
        "a 12s hook must trip the pacing warning instead of the 3.0s placeholder"
    assert res["estimated_duration"] == 12.0

    # without a measured duration the gate falls back to its 3.0s placeholder,
    # which is exactly why the renderers now record audio_duration per scene
    placeholder = qa.run_full_project_qa([{"idx": 0, "text": long_hook}], content_type="explainer")
    assert placeholder["estimated_duration"] == 3.0
    assert "hook_pacing" not in [i["check"] for i in placeholder["warnings"]]


# ------------------------------------------------------------ end-to-end render
def test_white_renderer_end_to_end_produces_the_photo_and_passes_qa(renderer, tmp_path, monkeypatch):
    """Runs the real render_project() into a temp dir and checks the pixels."""
    monkeypatch.setattr(renderer, "OUTPUT_DIR", str(tmp_path))
    full_qa = renderer.render_project()

    final = tmp_path / "Love_vs_Situationship_White_Final.mp4"
    assert final.exists()
    assert full_qa["approved"] is True, full_qa["failures"]
    assert full_qa["mp4_verified"] is True

    plain = renderer.create_white_background(720, 1280)
    frame_path = tmp_path / "probe.png"
    from ai_studio.util import ffmpeg_exe
    ff = ffmpeg_exe() or "ffmpeg"
    subprocess.check_call([ff, "-y", "-ss", "7.0", "-i", str(final), "-vframes", "1", str(frame_path)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    frame = cv2.imread(str(frame_path))
    assert frame is not None
    assert not np.array_equal(_card(plain), _card(frame)), \
        "the rendered video shows no internet photo in the card region"


# ------------------------------------------------------------ Edge-TTS and QA
def test_edge_tts_provider_and_validation(tmp_path):
    from ai_studio.engines import tts as tts_engine
    from ai_studio.engines.edge_tts_provider import EdgeTTSProvider

    provider = tts_engine.get_tts_provider()
    assert isinstance(provider, EdgeTTSProvider)

    # Test synthesis
    raw_audio = provider.synthesize("សាកល្បង", gender="male", emotion="neutral")
    assert len(raw_audio) > 1000

    # Test file synthesis and QA validation
    out_wav = str(tmp_path / "test_synth.wav")
    res = provider.synthesize_to_file("សាកល្បងសំឡេងខ្មែរ", out_wav, gender="male", emotion="happy")
    assert res["ok"] is True
    assert os.path.exists(out_wav)

    # Test QA gate audio validation
    assert qa.validate_khmer_audio(out_wav) is True

    # Short audio should fail QA validation
    short_wav = str(tmp_path / "short.wav")
    import wave
    with wave.open(short_wav, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(b"\x00" * 100)
    assert qa.validate_khmer_audio(short_wav) is False
