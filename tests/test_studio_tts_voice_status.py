"""TTS voice-installation badge: /api/status must report whether the real
Meta MMS VITS Khmer model (model.onnx) is installed, so the web UI can show a
green "native voice active" badge or a yellow placeholder warning.

Run: PYTHONPATH=. pytest tests/test_studio_tts_voice_status.py -q
"""
import os

from starlette.testclient import TestClient

from ai_studio.app import create_app
from ai_studio.engines import tts as tts_engine

MODEL_SUBDIR = os.path.join("models", "tts", "vits-mms-khm")


def _client(tmp_path):
    return TestClient(create_app(str(tmp_path)))


def _model_dir(tmp_path):
    d = tmp_path / "models" / "tts" / "vits-mms-khm"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_status_reports_placeholder_when_model_missing(tmp_path):
    r = _client(tmp_path).get("/api/status")
    assert r.status_code == 200, r.text
    tts = r.json()["tts"]

    # The badge keys strictly on model.onnx presence.
    assert tts["native_voice"] is False
    assert tts["placeholder_active"] is True
    assert tts["engine"] == "placeholder"
    assert tts["model_present"] is False
    assert tts["model"] is None
    assert tts["ready"] is False
    # The UI tells the user exactly which Windows script fixes this.
    assert tts["setup_script"] == "2_SETUP_KHMER_TTS.bat"
    assert tts["render_script"] == "3_RENDER_ALL_VIDEOS.bat"


def test_status_reports_native_voice_once_model_onnx_exists(tmp_path):
    d = _model_dir(tmp_path)
    (d / "model.onnx").write_bytes(b"FAKE-ONNX-WEIGHTS")
    (d / "tokens.txt").write_text("a 1\nb 2\n", encoding="utf-8")

    tts = _client(tmp_path).get("/api/status").json()["tts"]

    # Spec: model.onnx present -> green badge, regardless of python/CLI runtime
    assert tts["native_voice"] is True
    assert tts["placeholder_active"] is False
    assert tts["model_present"] is True
    assert tts["tokens_present"] is True
    assert tts["model"].replace("\\", "/").endswith("vits-mms-khm/model.onnx")
    assert tts["engine"] == "sherpa"

    # ready additionally needs a sherpa runtime (python API or CLI); whether
    # one exists in the test env, the flag must stay consistent with model state.
    assert tts["ready"] == bool(tts["runtime_python"] or tts["runtime_cli"])


def test_model_without_tokens_is_still_green_but_not_ready(tmp_path):
    d = _model_dir(tmp_path)
    (d / "model.onnx").write_bytes(b"FAKE")

    tts = _client(tmp_path).get("/api/status").json()["tts"]
    assert tts["native_voice"] is True       # badge follows model.onnx
    assert tts["tokens_present"] is False
    assert tts["ready"] is False             # cannot actually synthesize yet


def test_voice_status_helper_directly(tmp_path):
    """Unit-level check of the cheap filesystem probe."""
    app_state = create_app(str(tmp_path)).state.studio
    cfg = app_state.config()

    missing = tts_engine.voice_status(cfg)
    assert missing["native_voice"] is False
    assert missing["setup_script"]

    d = _model_dir(tmp_path)
    onnx = d / "model.onnx"
    onnx.write_bytes(b"x" * 1234)
    installed = tts_engine.voice_status(cfg)
    assert installed["native_voice"] is True
    assert installed["model_bytes"] == 1234
    assert installed["model_dir"].replace("\\", "/").endswith(MODEL_SUBDIR.replace("\\", "/"))
