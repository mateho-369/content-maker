"""Meme Engine & Intentional Reaction Support.

Provides intentional, high-retention meme moments:
- reaction images
- GIFs / animated loops
- visual punch-ins (fast scale zoom)
- freeze frames (comedic record-scratch pauses)
- meme captions
- SFX triggers

Intentional gating:
- Educational serious / emotional sad -> NO MEME
- Relatable / meme topics -> HIGH MEME retention
- Myth vs Fact -> SURPRISE REACTION
"""
import math
import os
import cv2
import numpy as np

MEME_TYPES = [
    "reaction_shock",
    "reaction_mindblown",
    "reaction_skeptical",
    "reaction_facepalm",
    "reaction_celebration",
    "reaction_confused",
    "dramatic_zoom",
    "freeze_frame_record_scratch",
    "meme_card",
]

# Curated original procedural reaction graphics (SVG-like geometric character reactions)
REACTION_PRESETS = {
    "reaction_shock": {
        "title": "SHOCKED REACTION",
        "bg_color": (25, 20, 35),
        "accent": "gasp",
        "sfx": "boom",
        "punch_scale": 1.35,
    },
    "reaction_mindblown": {
        "title": "MIND BLOWN",
        "bg_color": (30, 25, 50),
        "accent": "explosion",
        "sfx": "riser",
        "punch_scale": 1.25,
    },
    "reaction_skeptical": {
        "title": "SIDE EYE",
        "bg_color": (25, 30, 25),
        "accent": "squint",
        "sfx": "ding",
        "punch_scale": 1.15,
    },
    "reaction_facepalm": {
        "title": "FACEPALM",
        "bg_color": (20, 25, 35),
        "accent": "palm",
        "sfx": "pop",
        "punch_scale": 1.2,
    },
    "reaction_celebration": {
        "title": "VICTORY",
        "bg_color": (40, 35, 15),
        "accent": "sparks",
        "sfx": "applause",
        "punch_scale": 1.3,
    },
    "reaction_confused": {
        "title": "WAIT WHAT?",
        "bg_color": (30, 30, 30),
        "accent": "question",
        "sfx": "pop",
        "punch_scale": 1.15,
    },
}


def decide_meme_usage(content_type: str, topic: str, mood: str,
                      scene_idx: int, total_scenes: int,
                      side: str = "") -> tuple[bool, str, str, str]:
    """Content Director decision: Should this scene use a meme/reaction?

    Returns (use_meme, meme_type, sfx_cue, reasoning).
    """
    ct = (content_type or "").lower()
    t = (topic or "").lower()
    m = (mood or "").lower()
    s = (side or "").lower()

    # Rule 1: Emotional / Sad / Formal topics MUST NOT use memes
    if ct in ("emotional_sad", "sad_story") or any(w in m for w in ["sad", "sorrow", "grief"]):
        return False, "none", "", "Emotional/sad narrative requires solemn visual tone; memes forbidden."

    # Rule 2: Meme / Relatable content format ALWAYS prioritizes intentional meme beats
    if ct in ("meme_relatable", "meme", "relatable"):
        if scene_idx == 0:
            return True, "reaction_shock", "whoosh", "Hook viewer with immediate relatable reaction"
        if scene_idx == total_scenes - 1:
            return True, "reaction_facepalm", "boom", "Punchline comedic climax"
        return True, "reaction_mindblown", "pop", "Mid-video retention punch"

    # Rule 3: Myth vs Fact format uses reaction to emphasize the surprise of the myth
    if ct == "myth_vs_fact":
        if s == "myth" or scene_idx == 0:
            return True, "reaction_confused", "ding", "Highlight common misconception with confused/skeptical reaction"
        return False, "none", "", "Fact explanation uses clear informative graphics"

    # Rule 4: What-if surreal/bizarre consequences can benefit from mind-blown
    if ct == "what_if" and scene_idx == 1:
        return True, "reaction_mindblown", "riser", "Speculative twist emphasis"

    # Default for educational / explainer / serious
    return False, "none", "", "Standard informative scene focuses on character presentation"


def render_meme_clip(meme_type: str, headline: str, out_mp4: str,
                     duration: float = 2.0, width: int = 720, height: int = 1280,
                     fps: int = 25, punch_in: bool = True, freeze: bool = False,
                     background: dict | None = None) -> str:
    """Render a dynamic meme reaction clip with camera punch-in and visual impact.

    ``background``: a resolved ai_studio.backgrounds plate to put behind the
    reaction. The rays and the headline banner re-tint from the plate, so a white
    studio still reads as a meme and not as a blown-out accident.
    """
    m_info = REACTION_PRESETS.get(meme_type, REACTION_PRESETS["reaction_shock"])
    dur = max(0.5, float(duration))
    num_frames = int(round(dur * fps))

    bg_color = m_info["bg_color"]
    punch_max = m_info.get("punch_scale", 1.25) if punch_in else 1.0

    tmp_avi = out_mp4 + ".tmp.avi"
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    vw = cv2.VideoWriter(tmp_avi, fourcc, fps, (width, height))

    # Base graphic
    base = np.zeros((height, width, 3), dtype=np.uint8)
    base[:, :] = bg_color
    plate = None
    if background:
        from . import backgrounds as _bg
        plate = _bg.plate(background, width=width, height=height)
    if plate is not None:
        base = plate.copy()
        bg_color = tuple(int(round(c)) for c in base.reshape(-1, 3).mean(axis=0))

    # Concentric radial energy rays
    cx, cy = width // 2, int(height * 0.48)
    for angle in range(0, 360, 15):
        rad = math.radians(angle)
        rad2 = math.radians(angle + 7)
        pts = np.array([
            [cx, cy],
            [int(cx + math.cos(rad) * width * 1.5), int(cy + math.sin(rad) * height * 1.5)],
            [int(cx + math.cos(rad2) * width * 1.5), int(cy + math.sin(rad2) * height * 1.5)]
        ], np.int32)
        tint = (min(255, bg_color[0] + 25), min(255, bg_color[1] + 25), min(255, bg_color[2] + 35))
        cv2.fillPoly(base, [pts], tint)

    # Stylized reaction icon
    accent = m_info["accent"]
    if accent == "gasp":
        # Wide open eyes + shock mouth
        cv2.circle(base, (cx - 70, cy - 30), 45, (255, 255, 255), -1)
        cv2.circle(base, (cx + 70, cy - 30), 45, (255, 255, 255), -1)
        cv2.circle(base, (cx - 70, cy - 30), 18, (30, 20, 20), -1)
        cv2.circle(base, (cx + 70, cy - 30), 18, (30, 20, 20), -1)
        cv2.ellipse(base, (cx, cy + 70), (45, 65), 0, 0, 360, (20, 20, 20), -1)
        cv2.ellipse(base, (cx, cy + 70), (45, 65), 0, 0, 360, (240, 240, 240), 4)

    elif accent == "explosion":
        # Mind blown burst
        for r in (110, 85, 60):
            col = (int(255 - r), int(180 - r * 0.5), 255)
            cv2.circle(base, (cx, cy), r, col, -1)
        cv2.putText(base, "BOOM!", (cx - 100, cy + 15), cv2.FONT_HERSHEY_DUPLEX, 1.6, (20, 20, 30), 6)
        cv2.putText(base, "BOOM!", (cx - 100, cy + 15), cv2.FONT_HERSHEY_DUPLEX, 1.6, (255, 255, 255), 2)

    elif accent == "squint":
        # Skeptical side-eye
        cv2.ellipse(base, (cx - 65, cy), (40, 20), 0, 0, 360, (255, 255, 255), -1)
        cv2.ellipse(base, (cx + 65, cy), (40, 20), 0, 0, 360, (255, 255, 255), -1)
        cv2.circle(base, (cx - 45, cy), 14, (30, 30, 30), -1)
        cv2.circle(base, (cx + 85, cy), 14, (30, 30, 30), -1)

    else:
        # Default exclamation impact
        cv2.circle(base, (cx, cy), 90, (255, 215, 0), -1)
        cv2.putText(base, "!", (cx - 20, cy + 40), cv2.FONT_HERSHEY_SIMPLEX, 4.0, (20, 20, 20), 12)

    # Headline text banner at top
    text = (headline or m_info["title"]).upper()
    banner_y = int(height * 0.16)
    cv2.rectangle(base, (0, banner_y - 45), (width, banner_y + 35), (15, 15, 20), -1)
    font_scale = 1.1
    t_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, font_scale, 2)[0]
    tx = max(20, (width - t_size[0]) // 2)
    cv2.putText(base, text, (tx, banner_y + 10), cv2.FONT_HERSHEY_DUPLEX, font_scale, (255, 255, 255), 2, cv2.LINE_AA)

    try:
        for i in range(num_frames):
            t = float(i) / float(fps)
            frame = base.copy()

            # Punch-in zoom math (rapid 0.15s punch, then steady hold)
            if punch_in:
                zoom_phase = min(1.0, t / 0.18)
                scale = 1.0 + (punch_max - 1.0) * (1.0 - (1.0 - zoom_phase) ** 3)
                if scale > 1.01:
                    m_zoom = cv2.getRotationMatrix2D((cx, cy), 0, scale)
                    frame = cv2.warpAffine(frame, m_zoom, (width, height), flags=cv2.INTER_LINEAR,
                                           borderMode=cv2.BORDER_REFLECT)

            # Freeze frame comedic pause (desaturate after punch)
            if freeze and t > 0.4:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
                cv2.rectangle(frame, (cx - 160, int(height * 0.75) - 30),
                              (cx + 160, int(height * 0.75) + 30), (0, 0, 0), -1)
                cv2.putText(frame, "[ FREEZE FRAME ]", (cx - 140, int(height * 0.75) + 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)

            vw.write(frame)
        vw.release()

        # Remux
        cmd = [
            "ffmpeg", "-y", "-i", tmp_avi,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-pix_fmt", "yuv420p", out_mp4
        ]
        import subprocess
        subprocess.run(cmd, check=True, capture_output=True)
    finally:
        if os.path.exists(tmp_avi):
            try:
                os.remove(tmp_avi)
            except OSError:
                pass

    return out_mp4
