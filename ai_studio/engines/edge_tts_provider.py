"""Edge-TTS provider for high-quality Microsoft Neural Khmer voice synthesis."""
import asyncio
import os
import subprocess
import tempfile
from typing import Optional

import edge_tts
from ..util import ffmpeg_exe


class EdgeTTSProvider:
    """High-quality Microsoft Neural TTS for Khmer"""

    VOICES = {
        "male": "km-KH-PisethNeural",
        "female": "km-KH-SreymomNeural"
    }
    # The studio's voice picker sends any of these; resolving them here keeps the
    # id in settings readable (`"sreymom"` survives a rename of the short name).
    VOICE_ALIASES = {
        "piseth": "km-KH-PisethNeural", "male": "km-KH-PisethNeural",
        "sreymom": "km-KH-SreymomNeural", "female": "km-KH-SreymomNeural",
        "km-kh-pisethneural": "km-KH-PisethNeural",
        "km-kh-sreymomneural": "km-KH-SreymomNeural",
    }

    @classmethod
    def resolve_voice(cls, voice=None, gender=None):
        """`"sreymom"` / `"female"` / `"km-KH-SreymomNeural"` → the short name."""
        for cand in (voice, gender):
            key = str(cand or "").strip().lower()
            if not key:
                continue
            if key in cls.VOICE_ALIASES:
                return cls.VOICE_ALIASES[key]
            if key.startswith("km-") or "-" in key:
                return str(cand).strip()
        return cls.VOICES.get(str(gender or "male"), cls.VOICES["male"])

    @classmethod
    def catalog(cls, available=None):
        """What the Voices tab lists under "TTS voices" — ids the studio accepts.

        `available` (from :func:`ai_studio.engines.tts.available_engines`) decides
        whether the row is selectable or carries the fix-it note, so a machine
        without the package shows the reason instead of a silent fallback.
        """
        out = []
        for label, short, gender in (("Piseth", "km-KH-PisethNeural", "male"),
                                     ("Sreymom", "km-KH-SreymomNeural", "female")):
            out.append({
                "id": f"edge_tts:{short}",
                "label": f"⚡ Edge-TTS {label} ({'Male' if gender == 'male' else 'Female'})",
                "provider": "edge_tts", "voice": short, "gender": gender,
                "engine": "edge_tts",
                "emotions": sorted(cls.EMOTION_PROFILES),
                "needs_network": True,
                "available": True if available is None else bool(available.get("edge_tts")),
                "note": ("Microsoft neural voice — needs internet on the first call"
                         if available is None or available.get("edge_tts") else
                         "pip install edge-tts (requirements-studio.txt) to enable"),
            })
        return out

    EMOTION_PROFILES = {
        "happy": {"rate": "+10%", "pitch": "+2Hz"},
        "sad": {"rate": "-10%", "pitch": "-2Hz"},
        "excited": {"rate": "+20%", "pitch": "+5Hz"},
        "serious": {"rate": "-5%", "pitch": "0Hz"},
        "neutral": {"rate": "0%", "pitch": "0Hz"},
        "calm": {"rate": "-2%", "pitch": "0Hz"},
        "confused": {"rate": "-5%", "pitch": "+2Hz"},
        "storytelling": {"rate": "-4%", "pitch": "-1Hz"},
        "surprised": {"rate": "+15%", "pitch": "+4Hz"},
        "strong": {"rate": "+5%", "pitch": "+1Hz"},
        "soft": {"rate": "-8%", "pitch": "-1Hz"},
        "emotional": {"rate": "-6%", "pitch": "-2Hz"}
    }

    def __init__(self, default_gender: str = "male"):
        self.default_gender = default_gender
        self.default_voice = self.VOICES.get(default_gender, "km-KH-PisethNeural")

    async def _synthesize_async(self, text: str, voice: str, emotion: str = "neutral") -> bytes:
        profile = self.EMOTION_PROFILES.get(emotion, self.EMOTION_PROFILES["neutral"])
        rate = profile.get("rate", "0%")
        pitch = profile.get("pitch", "0Hz")
        try:
            communicate = edge_tts.Communicate(
                text,
                voice,
                rate=rate,
                pitch=pitch
            )
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            if audio_data and len(audio_data) > 200:
                return audio_data, True
        except Exception:
            # Offline, sandboxed, or Microsoft blocked: synthesise locally so the
            # pipeline still has audio to time against — but the caller is told
            # this is NOT the neural voice (see synthesize_to_file).
            return self._generate_offline_speech_mp3(text, voice, emotion), False

        return self._generate_offline_speech_mp3(text, voice, emotion), False

    def _generate_offline_speech_mp3(self, text: str, voice: str, emotion: str = "neutral") -> bytes:
        """High-resolution vocal formant synthesis for offline / CI environments."""
        import numpy as np

        sr = 24000
        clean_len = max(len(text.strip()), 4)
        dur = max(2.5, min(15.0, clean_len * 0.085 + 1.2))
        n = int(dur * sr)
        t = np.linspace(0, dur, n, endpoint=False)

        is_female = "female" in voice.lower() or "sreymom" in voice.lower()
        base_f0 = 220.0 if is_female else 135.0

        profile = self.EMOTION_PROFILES.get(emotion, self.EMOTION_PROFILES["neutral"])
        pitch_val = profile.get("pitch", "0Hz")
        shift = 1.05 if "+5Hz" in pitch_val or "+4Hz" in pitch_val else (0.95 if "-2Hz" in pitch_val else 1.0)
        f0 = base_f0 * shift * (1.0 + 0.05 * np.sin(2 * np.pi * 1.8 * t) + 0.02 * np.cos(2 * np.pi * 3.6 * t))
        phase = 2 * np.pi * np.cumsum(f0) / sr

        f1, f2, f3 = (700, 2100, 3100) if is_female else (550, 1600, 2700)
        sig = (0.50 * np.sin(phase) +
               0.28 * np.sin(2 * phase) +
               0.14 * np.sin(3 * phase) +
               0.08 * np.sin(2 * np.pi * f1 * t) +
               0.05 * np.sin(2 * np.pi * f2 * t) +
               0.03 * np.sin(2 * np.pi * f3 * t))

        syl_env = 0.55 + 0.45 * np.maximum(0, np.sin(2 * np.pi * 4.2 * t))
        sig = sig * syl_env
        ramp = int(0.04 * sr)
        sig[:ramp] *= np.linspace(0, 1, ramp)
        sig[-ramp:] *= np.linspace(1, 0, ramp)

        pcm = (np.clip(sig, -0.95, 0.95) * 24000).astype(np.int16).tobytes()
        try:
            ff = ffmpeg_exe() or "ffmpeg"
            cmd = [ff, '-y', '-f', 's16le', '-ar', str(sr), '-ac', '1', '-i', 'pipe:0', '-f', 'mp3', 'pipe:1']
            res = subprocess.run(cmd, input=pcm, capture_output=True, check=True)
            return res.stdout
        except Exception:
            return pcm

    def synthesize(self, text: str, gender: str = "male", emotion: str = "neutral",
                   voice: str = None) -> bytes:
        data, _real = self.synthesize_audio(text, gender=gender, emotion=emotion, voice=voice)
        return data

    def synthesize_audio(self, text: str, gender: str = "male", emotion: str = "neutral",
                         voice: str = None):
        """(mp3 bytes, from_network). The flag matters: a local stand-in is fine
        for timing previews but must never be sold as the neural voice."""
        v = self.resolve_voice(voice, gender)
        return asyncio.run(self._synthesize_async(text, v, emotion))

    def synthesize_to_file(self, text: str, out_path: str, gender: str = "male",
                           emotion: str = "neutral", voice: str = None) -> dict:
        voice = self.resolve_voice(voice, gender)
        data, from_network = self.synthesize_audio(text, gender=gender, emotion=emotion, voice=voice)
        if not data:
            return {"ok": False, "reason": "Edge-TTS produced empty audio"}

        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        if out_path.lower().endswith(".wav"):
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
                tf.write(data)
                tmp_mp3 = tf.name
            ff = ffmpeg_exe() or "ffmpeg"
            try:
                subprocess.run([
                    ff, "-y", "-i", tmp_mp3,
                    "-ar", "44100", "-ac", "1", out_path
                ], check=True, capture_output=True)
            finally:
                if os.path.exists(tmp_mp3):
                    try:
                        os.remove(tmp_mp3)
                    except OSError:
                        pass
        else:
            with open(out_path, "wb") as f:
                f.write(data)

        dur = 0.0
        try:
            import wave
            with wave.open(out_path, 'rb') as wf:
                dur = wf.getnframes() / float(wf.getframerate())
        except Exception:
            pass

        return {
            "ok": True,
            # An honest engine label: QA, the run log and the scene card all quote
            # this back, so it has to distinguish neural speech from the stand-in.
            "engine": (f"edge-tts ({voice})" if from_network
                       else f"edge-tts-local-stand-in ({voice})"),
            "provider": "edge_tts",
            "voice": voice,
            "real_speech": bool(from_network),
            "network": bool(from_network),
            "duration": dur,
            "path": out_path,
            **({} if from_network else {
                "reason": "Microsoft's edge-tts endpoint was unreachable, so this audio was "
                          "generated locally — the words and timing are real, the voice is not. "
                          "Check your internet connection and run the stage again."}),
        }
