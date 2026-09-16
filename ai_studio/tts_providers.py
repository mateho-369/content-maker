"""TTS Provider Architecture & Emotional Voice Processing Layer.

Provides clean multi-backend TTS abstraction:
  - Local Khmer TTS (sherpa-onnx VITS / PyTorch transformers)
  - Hugging Face Inference API / Providers TTS
  - Multi-lingual Fallback (Kokoro)
  - Speech-shaped Placeholder (honest durations)

Plus a professional acoustic emotion pipeline applying safe, musical prosody
shaping (speed, pitch, dynamics, timbre) across 10 emotional styles.
"""
from __future__ import annotations

import abc
import math
import os
import shutil
import subprocess
from typing import Any

from . import khmer
from .util import ensure_dir, media_duration, read_wav, write_wav

EMOTIONAL_STYLES = {
    "calm": {
        "speed": 0.96,
        "pitch_semitones": 0.0,
        "energy": 0.90,
        "pause_factor": 1.1,
        "desc": "Even, gentle, contemplative rhythm",
    },
    "soft": {
        "speed": 0.92,
        "pitch_semitones": -0.4,
        "energy": 0.78,
        "pause_factor": 1.15,
        "desc": "Quiet, warm, intimate tone",
    },
    "strong": {
        "speed": 1.05,
        "pitch_semitones": 0.4,
        "energy": 1.22,
        "pause_factor": 0.95,
        "desc": "Decisive, firm, authoritative projection",
    },
    "happy": {
        "speed": 1.10,
        "pitch_semitones": 1.2,
        "energy": 1.14,
        "pause_factor": 0.85,
        "desc": "Upbeat, buoyant, bright inflection",
    },
    "sad": {
        "speed": 0.86,
        "pitch_semitones": -1.3,
        "energy": 0.72,
        "pause_factor": 1.35,
        "desc": "Somber, slower, melancholic cadence",
    },
    "serious": {
        "speed": 0.98,
        "pitch_semitones": -0.5,
        "energy": 1.08,
        "pause_factor": 1.05,
        "desc": "Measured, controlled, focused delivery",
    },
    "excited": {
        "speed": 1.18,
        "pitch_semitones": 1.8,
        "energy": 1.25,
        "pause_factor": 0.80,
        "desc": "High energy, rapid, punchy accent",
    },
    "surprised": {
        "speed": 1.12,
        "pitch_semitones": 2.0,
        "energy": 1.15,
        "pause_factor": 0.90,
        "desc": "Elevated pitch, alert, sudden emphasis",
    },
    "storytelling": {
        "speed": 0.94,
        "pitch_semitones": -0.3,
        "energy": 0.98,
        "pause_factor": 1.20,
        "desc": "Rich dynamic contrast, expressive pauses",
    },
    "emotional": {
        "speed": 0.90,
        "pitch_semitones": -0.8,
        "energy": 0.85,
        "pause_factor": 1.25,
        "desc": "Vulnerable, deep narrative presence",
    },
}

DEFAULT_STYLE = "calm"


# ------------------------------------------------------------- Audio Processing
def apply_emotional_style(input_wav: str, output_wav: str,
                          emotion: str = "calm",
                          speed_override: float | None = None,
                          pitch_override: float | None = None) -> str:
    """Apply safe acoustic emotional modulation to a raw speech WAV file.

    Modulates:
      - tempo/speed (safe clamp 0.80x .. 1.28x)
      - pitch shift via asetrate/aresample (safe clamp -2.0 .. +2.2 semitones)
      - dynamic energy / volume
      - subtle presence EQ
    """
    if not os.path.exists(input_wav):
        raise FileNotFoundError(f"Source WAV not found: {input_wav}")

    style = EMOTIONAL_STYLES.get(emotion.lower(), EMOTIONAL_STYLES[DEFAULT_STYLE])

    target_speed = float(speed_override if speed_override is not None else style["speed"])
    target_pitch = float(pitch_override if pitch_override is not None else style["pitch_semitones"])
    energy = float(style["energy"])

    # Safe boundaries to avoid robotic metallic distortion
    target_speed = max(0.80, min(1.28, target_speed))
    target_pitch = max(-2.2, min(2.5, target_pitch))
    energy = max(0.65, min(1.35, energy))

    # Read source sample rate
    _x, sr = read_wav(input_wav)
    sr = int(sr or 44100)

    # Calculate pitch resampling factor: factor = 2^(semitones / 12)
    pitch_factor = 2.0 ** (target_pitch / 12.0)
    virtual_sr = int(round(sr * pitch_factor))
    tempo_compensation = target_speed / pitch_factor

    # FFmpeg atempo requires 0.5 <= atempo <= 2.0 (we are well within 0.7..1.4)
    filters = []

    if abs(pitch_factor - 1.0) > 0.005:
        filters.append(f"asetrate={virtual_sr}")
        filters.append(f"aresample={sr}")

    if abs(tempo_compensation - 1.0) > 0.005:
        filters.append(f"atempo={tempo_compensation:.4f}")

    if abs(energy - 1.0) > 0.01:
        filters.append(f"volume={energy:.3f}")

    # EQ coloration per emotion
    if emotion in ("soft", "sad", "emotional"):
        filters.append("equalizer=f=3200:t=q:w=1.2:g=-2")  # soften highs
        filters.append("equalizer=f=280:t=q:w=1.0:g=+1.5")  # warm lows
    elif emotion in ("happy", "excited", "surprised"):
        filters.append("equalizer=f=3500:t=q:w=1.0:g=+2")   # crisp clarity
    elif emotion in ("strong", "serious"):
        filters.append("equalizer=f=200:t=q:w=1.0:g=+1.8")  # authoritative chest tone

    af_arg = ",".join(filters) if filters else "anull"

    cmd = ["ffmpeg", "-y", "-i", input_wav, "-af", af_arg, output_wav]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_wav


# ------------------------------------------------------------- Base Provider
class BaseTTSProvider(abc.ABC):
    id: str
    name: str
    is_local: bool
    requires_api_key: bool

    @abc.abstractmethod
    def is_available(self, cfg: dict) -> bool:
        pass

    @abc.abstractmethod
    def synthesize_raw(self, text: str, out_wav: str, cfg: dict, progress=None) -> dict:
        pass

    def synthesize(self, text: str, out_wav: str, cfg: dict,
                   emotion: str = "calm", speed: float = 1.0,
                   progress=None) -> dict:
        """Synthesize text and pass through the emotional style pipeline."""
        clean_text = khmer.spoken_text(text or "")
        clean_text = khmer.strip_emoji_and_marks(clean_text)
        if not clean_text:
            return {"ok": False, "reason": "empty text", "provider": self.id}

        raw_tmp = out_wav + ".raw.wav"
        ensure_dir(os.path.dirname(out_wav) or ".")

        try:
            res = self.synthesize_raw(clean_text, raw_tmp, cfg, progress=progress)
            if not res.get("ok") or not os.path.exists(raw_tmp):
                return res

            # Apply emotional post-processing
            speed_factor = float(speed or 1.0)
            apply_emotional_style(raw_tmp, out_wav, emotion=emotion, speed_override=speed_factor)
            dur = media_duration(out_wav, res.get("duration", 0.0))

            res["path"] = out_wav
            res["duration"] = dur
            res["emotion"] = emotion
            res["speed"] = speed_factor
            res["provider"] = self.id
            return res
        finally:
            if os.path.exists(raw_tmp):
                try:
                    os.remove(raw_tmp)
                except OSError:
                    pass


# ------------------------------------------------------------- Local Sherpa ONNX Provider
class LocalSherpaTTSProvider(BaseTTSProvider):
    id = "local_sherpa"
    name = "Local Khmer TTS (sherpa-onnx / MMS-VITS)"
    is_local = True
    requires_api_key = False

    def is_available(self, cfg: dict) -> bool:
        from .engines import tts as tts_engine
        onnx, _tok, _dir = tts_engine.resolve_model(cfg)
        return bool(onnx and (tts_engine._python_api() or tts_engine.sherpa_bin(cfg)))

    def synthesize_raw(self, text: str, out_wav: str, cfg: dict, progress=None) -> dict:
        from .engines import tts as tts_engine
        attempts = []
        res = tts_engine._try_sherpa(text, out_wav, cfg, progress, attempts)
        if res.get("ok"):
            return res
        return {"ok": False, "reason": "; ".join(attempts), "provider": self.id}


# ------------------------------------------------------------- Hugging Face API Provider
class HuggingFaceTTSProvider(BaseTTSProvider):
    id = "huggingface"
    name = "Hugging Face Inference API / Providers"
    is_local = False
    requires_api_key = True

    def is_available(self, cfg: dict) -> bool:
        tcfg = cfg.get("tts", {})
        token = os.environ.get("HF_TOKEN") or tcfg.get("hf_token")
        return bool(token)

    def synthesize_raw(self, text: str, out_wav: str, cfg: dict, progress=None) -> dict:
        tcfg = cfg.get("tts", {})
        token = os.environ.get("HF_TOKEN") or tcfg.get("hf_token")
        if not token:
            return {"ok": False, "reason": "HF_TOKEN not configured in environment or settings", "provider": self.id}

        model_id = tcfg.get("hf_model") or "facebook/mms-tts-khm"

        try:
            import urllib.request
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "KhmerAIStudio/3.0"
            }
            import json
            req_data = json.dumps({"inputs": text}).encode("utf-8")
            url = f"https://api-inference.huggingface.co/models/{model_id}"
            req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")

            with urllib.request.urlopen(req, timeout=30) as resp:
                audio_bytes = resp.read()

            with open(out_wav, "wb") as f:
                f.write(audio_bytes)

            dur = media_duration(out_wav, 0.0)
            return {"ok": True, "engine": f"hf-inference:{model_id}", "duration": dur,
                    "real_speech": True, "provider": self.id}
        except Exception as e:
            return {"ok": False, "reason": f"Hugging Face API error: {str(e)[:180]}", "provider": self.id}


# ------------------------------------------------------------- Edge-TTS Provider
class EdgeTTSStudioProvider(BaseTTSProvider):
    id = "edge_tts"
    name = "Microsoft Neural TTS (Edge-TTS km-KH-PisethNeural)"
    is_local = False
    requires_api_key = False

    def is_available(self, cfg: dict) -> bool:
        try:
            from .engines.edge_tts_provider import EdgeTTSProvider
            return True
        except Exception:
            return False

    def synthesize_raw(self, text: str, out_wav: str, cfg: dict, progress=None) -> dict:
        from .engines.edge_tts_provider import EdgeTTSProvider
        p = EdgeTTSProvider()
        return p.synthesize_to_file(text, out_wav, gender="male", emotion="neutral")


# ------------------------------------------------------------- Placeholder Provider
class PlaceholderTTSProvider(BaseTTSProvider):
    id = "placeholder"
    name = "Speech-Shaped Realistic Rhythm (Offline Fallback)"
    is_local = True
    requires_api_key = False

    def is_available(self, cfg: dict) -> bool:
        return True

    def synthesize_raw(self, text: str, out_wav: str, cfg: dict, progress=None) -> dict:
        from .engines import tts as tts_engine
        attempts = []
        return tts_engine._placeholder(text, out_wav, cfg, attempts)


# ------------------------------------------------------------- TTS Registry & Manager
PROVIDERS: dict[str, BaseTTSProvider] = {
    "edge_tts": EdgeTTSStudioProvider(),
    "local_sherpa": LocalSherpaTTSProvider(),
    "huggingface": HuggingFaceTTSProvider(),
    "placeholder": PlaceholderTTSProvider(),
}


def get_provider(provider_id: str | None = None) -> BaseTTSProvider:
    if provider_id and provider_id in PROVIDERS:
        return PROVIDERS[provider_id]
    return PROVIDERS["placeholder"]


def list_providers(cfg: dict) -> list[dict]:
    out = []
    for pid, prov in PROVIDERS.items():
        out.append({
            "id": pid,
            "name": prov.name,
            "is_local": prov.is_local,
            "requires_api_key": prov.requires_api_key,
            "available": prov.is_available(cfg),
        })
    return out


def synthesize_speech(text: str, out_wav: str, cfg: dict,
                      provider_id: str = "auto",
                      emotion: str = "calm",
                      speed: float = 1.0,
                      progress=None) -> dict:
    """Unified entry point for speech synthesis across all providers."""
    # Resolve provider
    chosen = provider_id
    if chosen == "auto" or chosen not in PROVIDERS:
        # Check Edge-TTS FIRST (most reliable on Windows & across environments)
        if PROVIDERS["edge_tts"].is_available(cfg):
            chosen = "edge_tts"
        elif PROVIDERS["local_sherpa"].is_available(cfg):
            chosen = "local_sherpa"
        elif PROVIDERS["huggingface"].is_available(cfg):
            chosen = "huggingface"
        else:
            chosen = "placeholder"

    prov = PROVIDERS.get(chosen, PROVIDERS["placeholder"])
    res = prov.synthesize(text, out_wav, cfg, emotion=emotion, speed=speed, progress=progress)

    # Fallback to placeholder if primary provider fails
    if not res.get("ok") and chosen != "placeholder":
        res_ph = PROVIDERS["placeholder"].synthesize(text, out_wav, cfg, emotion=emotion, speed=speed, progress=progress)
        res_ph["fallback_from"] = chosen
        res_ph["primary_reason"] = res.get("reason")
        return res_ph

    return res
