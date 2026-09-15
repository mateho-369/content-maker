"""Character Action System: Deterministic context-aware character animations.

Provides a rich library of procedural and expressive actions for characters
while ensuring strict visual consistency (using the character's real asset/cutout
rather than stochastic generative hallucination).

Actions:
  - talking (audio talk-pulse + natural breathing)
  - pointing (pointing_left, pointing_right, pointing_up)
  - looking_left / looking_right
  - surprised
  - happy
  - sad
  - thinking
  - confused
  - laughing
  - crying
  - shocked
  - walking
  - sitting
  - reacting
  - celebrating
  - frustrated
  - explaining
  - holding_object (with props: phone, card, document, pointer, magnifier, book, etc.)
"""
import math
import os
import cv2
import numpy as np

CHARACTER_ACTIONS = [
    "neutral",
    "talking",
    "pointing_left",
    "pointing_right",
    "pointing_up",
    "pointing_down",
    "explaining",
    "happy",
    "very_happy",
    "sad",
    "crying",
    "shocked",
    "surprised",
    "confused",
    "thinking",
    "angry",
    "laughing",
    "celebrating",
    "embarrassed",
    "disappointed",
    "looking_left",
    "looking_right",
    "walking",
    "sitting",
    "reacting",
    "frustrated",
    "holding_object",
]

PROPS = [
    "phone",
    "card",
    "document",
    "pointer",
    "magnifier",
    "book",
    "trophy",
    "microphone",
]

ACTION_METADATA = {
    "talking": {"desc": "Audio-synced speech rhythm with natural body pulse", "category": "dialogue"},
    "pointing_left": {"desc": "Directs viewer attention to the left info card", "category": "presentation"},
    "pointing_right": {"desc": "Directs viewer attention to the right info card", "category": "presentation"},
    "pointing_up": {"desc": "Emphasizes top headline or key takeaway", "category": "presentation"},
    "pointing_down": {"desc": "Emphasizes lower subtitle, summary, or link", "category": "presentation"},
    "looking_left": {"desc": "Curious gaze toward left visual element", "category": "reaction"},
    "looking_right": {"desc": "Curious gaze toward right visual element", "category": "reaction"},
    "surprised": {"desc": "Eyes wide, slight backward recoil, energetic pop", "category": "reaction"},
    "happy": {"desc": "Warm, buoyant posture with cheerful rhythm", "category": "emotion"},
    "very_happy": {"desc": "Exuberant double bounce with celebration sparkles", "category": "emotion"},
    "sad": {"desc": "Lowered posture, slow subtle movement, reflective", "category": "emotion"},
    "thinking": {"desc": "Contemplative tilt, floating thought cues", "category": "cognitive"},
    "confused": {"desc": "Head tilt wobble, questioning posture", "category": "cognitive"},
    "laughing": {"desc": "Upbeat comedic chuckle vibration", "category": "emotion"},
    "crying": {"desc": "Sorrowful downward slump with subtle tear motion", "category": "emotion"},
    "shocked": {"desc": "Dramatic zoom punch-in with high-energy jitter", "category": "reaction"},
    "angry": {"desc": "Tense posture with heated pulse and steam puffs", "category": "emotion"},
    "embarrassed": {"desc": "Shy look away with blushing cheek glow", "category": "emotion"},
    "disappointed": {"desc": "Heavy sigh sag and dejected posture", "category": "emotion"},
    "neutral": {"desc": "Calm, composed baseline pose with natural breathing", "category": "posture"},
    "walking": {"desc": "Stepped lateral sway and vertical step bounce", "category": "locomotion"},
    "sitting": {"desc": "Anchored seated posture with calm breathing", "category": "posture"},
    "reacting": {"desc": "Sudden turn toward camera with expression shift", "category": "reaction"},
    "celebrating": {"desc": "Victorious celebration bounce with celebratory sparks", "category": "emotion"},
    "frustrated": {"desc": "Intense head shake and exasperated posture", "category": "emotion"},
    "explaining": {"desc": "Alternating conversational gestures with forward lean", "category": "dialogue"},
    "holding_object": {"desc": "Presenting or using an in-hand prop", "category": "prop"},
}


def normalize_action(action: str) -> str:
    """Normalize any string into a recognized character action."""
    act = str(action or "").strip().lower().replace("-", "_")
    if act in CHARACTER_ACTIONS:
        return act
    if "point" in act:
        if "left" in act: return "pointing_left"
        if "right" in act: return "pointing_right"
        if "up" in act: return "pointing_up"
        if "down" in act: return "pointing_down"
        return "pointing_right"
    if "very_happy" in act or "super_happy" in act: return "very_happy"
    if "look" in act:
        if "left" in act: return "looking_left"
        if "right" in act: return "looking_right"
        return "looking_left"
    if "laugh" in act: return "laughing"
    if "cry" in act: return "crying"
    if "shock" in act: return "shocked"
    if "surpris" in act: return "surprised"
    if "think" in act: return "thinking"
    if "confus" in act: return "confused"
    if "angry" in act or "mad" in act: return "angry"
    if "embarrass" in act or "blush" in act: return "embarrassed"
    if "disappoint" in act: return "disappointed"
    if "neutral" in act: return "neutral"
    if "walk" in act: return "walking"
    if "sit" in act: return "sitting"
    if "celebrat" in act or "win" in act: return "celebrating"
    if "frustrat" in act: return "frustrated"
    if "explain" in act: return "explaining"
    if "hold" in act or "prop" in act or "use" in act: return "holding_object"
    if "sad" in act or "sorrow" in act: return "sad"
    if "happy" in act or "joy" in act: return "happy"
    if "react" in act: return "reacting"
    return "talking"


def action_for_scene(mood_tag: str, text: str, side: str = "", content_type: str = "") -> tuple[str, str | None]:
    """Determine the most effective character action and optional prop for a scene."""
    mood = (mood_tag or "").lower()
    t = (text or "").lower()
    ct = (content_type or "").lower()
    side = (side or "").lower()

    # Content-type structural decisions
    if ct == "compare":
        if side in ("a", "1", "meaning-1", "option_1"):
            return "pointing_left", None
        if side in ("b", "2", "meaning-2", "option_2"):
            return "pointing_right", None
        return "explaining", None

    if ct == "myth_vs_fact":
        if side == "myth":
            return "confused", None
        if side == "fact":
            return "pointing_up", None
        return "explaining", None

    if ct == "choose":
        if side == "takeaway":
            return "celebrating", "card"
        return "explaining", "card"

    if ct == "quick_tip":
        return "pointing_up", "pointer"

    if ct in ("meme", "meme_relatable", "relatable"):
        if any(w in mood for w in ["shock", "surpris"]): return "shocked", None
        if any(w in mood for w in ["sad", "cry"]): return "crying", None
        if any(w in mood for w in ["frustrat", "angry"]): return "frustrated", None
        return "laughing", None

    # Mood-based matching
    if any(m in mood for m in ["shock", "gasp"]): return "shocked", None
    if any(m in mood for m in ["surpris"]): return "surprised", None
    if any(m in mood for m in ["laugh", "funny"]): return "laughing", None
    if any(m in mood for m in ["sad", "sorrow", "grief"]): return "sad", None
    if any(m in mood for m in ["cry", "tears"]): return "crying", None
    if any(m in mood for m in ["think", "ponder", "wonder"]): return "thinking", None
    if any(m in mood for m in ["confus", "doubt", "puzzl"]): return "confused", None
    if any(m in mood for m in ["celebrat", "proud", "victory", "joy"]): return "celebrating", "trophy"
    if any(m in mood for m in ["frustrat", "annoy", "angry"]): return "frustrated", None
    if any(m in mood for m in ["walk", "journey", "step", "move"]): return "walking", None
    if any(m in mood for m in ["sit", "rest", "calm", "still"]): return "sitting", None
    if any(m in mood for m in ["happy", "cheerful", "warm"]): return "happy", None
    if any(m in mood for m in ["explain", "teach", "learn"]): return "explaining", None

    return "talking", None


# ------------------------------------------------------------- Motion transforms
def compute_action_transform(action: str, t: float, duration: float, has_audio_pulse: bool = False, pulse_level: float = 0.0):
    """Compute (scale_x, scale_y, offset_x_px, offset_y_px, rotation_deg, alpha, effect_data) for an action at time t."""
    dur = max(0.1, duration)
    p = t / dur
    cycle = t * 2.0 * math.pi

    sx, sy = 1.0, 1.0
    ox, oy = 0.0, 0.0
    rot = 0.0
    alpha = 1.0
    effects = {}

    if action == "talking":
        # Natural breathing + audio talk pulse
        pulse = pulse_level if has_audio_pulse else (0.5 + 0.5 * math.sin(t * 14.0)) * 0.04
        breathe = math.sin(cycle * 0.8) * 0.015
        sy = 1.0 + breathe + pulse * 0.06
        sx = 1.0 - breathe * 0.5 - pulse * 0.02
        oy = math.sin(cycle * 0.8) * 6.0

    elif action == "pointing_left":
        # Lean slightly left, extend gesture
        enter = min(1.0, t / 0.4)
        ox = -45.0 * enter + math.sin(cycle * 0.5) * 4.0
        rot = -3.5 * enter
        sy = 1.0 + math.sin(cycle * 0.8) * 0.015
        effects["gesture"] = "point_left"

    elif action == "pointing_right":
        enter = min(1.0, t / 0.4)
        ox = 45.0 * enter + math.sin(cycle * 0.5) * 4.0
        rot = 3.5 * enter
        sy = 1.0 + math.sin(cycle * 0.8) * 0.015
        effects["gesture"] = "point_right"

    elif action == "pointing_up":
        enter = min(1.0, t / 0.35)
        oy = -35.0 * enter + math.sin(cycle * 0.6) * 4.0
        sy = 1.02 + 0.02 * enter
        effects["gesture"] = "point_up"

    elif action == "pointing_down":
        enter = min(1.0, t / 0.35)
        oy = 30.0 * enter + math.sin(cycle * 0.6) * 3.0
        sy = 0.98 + 0.01 * enter
        effects["gesture"] = "point_down"

    elif action == "neutral":
        breathe = math.sin(cycle * 0.6) * 0.01
        sy = 1.0 + breathe
        sx = 1.0 - breathe * 0.5
        oy = math.sin(cycle * 0.6) * 4.0

    elif action == "very_happy":
        double_bounce = abs(math.sin(t * 5.0 * math.pi))
        oy = -55.0 * double_bounce
        sy = 1.08 + 0.08 * double_bounce
        sx = 0.95 - 0.04 * double_bounce
        rot = math.sin(t * 3.5 * math.pi) * 3.5
        effects["accent"] = "sparkles"

    elif action == "angry":
        jitter = math.sin(t * 28.0 * math.pi) * 5.0
        ox = jitter
        sy = 1.03 + 0.02 * math.sin(cycle * 2.0)
        rot = math.sin(t * 14.0 * math.pi) * 2.0
        effects["accent"] = "steam_puff"

    elif action == "embarrassed":
        rot = 4.0 + math.sin(cycle * 0.5) * 2.0
        ox = -20.0
        sy = 0.96 + math.sin(cycle * 0.5) * 0.01
        effects["accent"] = "blush"

    elif action == "disappointed":
        sag = min(1.0, t / 0.6)
        oy = 35.0 * sag + math.sin(cycle * 0.3) * 3.0
        sy = 0.92 - 0.02 * sag
        rot = -3.0 * sag
        effects["accent"] = "sigh"

    elif action == "looking_left":
        ox = -30.0 + math.sin(cycle * 0.4) * 6.0
        rot = -2.5

    elif action == "looking_right":
        ox = 30.0 + math.sin(cycle * 0.4) * 6.0
        rot = 2.5

    elif action == "surprised":
        # Rapid upward pop and slight recoil
        if t < 0.25:
            k = t / 0.25
            sy = 1.0 + 0.12 * math.sin(k * math.pi)
            sx = 1.0 - 0.06 * math.sin(k * math.pi)
            oy = -50.0 * k
        else:
            sy = 1.04 + math.sin(cycle * 1.5) * 0.02
            oy = -25.0 + math.sin(cycle * 1.5) * 4.0
        effects["accent"] = "surprise_burst"

    elif action == "happy":
        # Bouncy upbeat oscillation
        bounce = abs(math.sin(t * 3.5 * math.pi))
        oy = -40.0 * bounce
        sy = 1.0 + 0.05 * bounce
        sx = 1.0 - 0.03 * bounce
        rot = math.sin(t * 2.0 * math.pi) * 2.0
        effects["accent"] = "sparkles"

    elif action == "sad":
        # Slumped posture, gentle slow sway
        sy = 0.94 + math.sin(cycle * 0.4) * 0.01
        oy = 25.0 + math.sin(cycle * 0.4) * 4.0
        rot = -1.5

    elif action == "thinking":
        # Tilting head, hand toward chin
        rot = 4.0 + math.sin(cycle * 0.6) * 1.5
        oy = math.sin(cycle * 0.5) * 5.0
        ox = 10.0
        effects["accent"] = "thought_bubble"

    elif action == "confused":
        # Alternating curious wobble
        rot = math.sin(t * 2.5 * math.pi) * 5.5
        ox = math.sin(t * 1.25 * math.pi) * 12.0
        effects["accent"] = "question_mark"

    elif action == "laughing":
        # Rapid energetic chuckling bounce
        chuckle = abs(math.sin(t * 9.0 * math.pi))
        oy = -18.0 * chuckle
        sy = 1.0 + 0.04 * chuckle
        rot = math.sin(t * 4.5 * math.pi) * 2.5
        effects["accent"] = "laugh_tears"

    elif action == "crying":
        # Downward slump with rhythmic tremor
        tremor = math.sin(t * 12.0 * math.pi) * 2.0
        oy = 30.0 + tremor
        sy = 0.92
        rot = -2.0
        effects["accent"] = "teardrops"

    elif action == "shocked":
        # Fast punch-in zoom and chaotic jitter
        zoom = 1.15 if t > 0.1 else (1.0 + 1.5 * t)
        jitter_x = math.sin(t * 35.0) * 8.0
        jitter_y = math.cos(t * 30.0) * 8.0
        sx, sy = zoom, zoom
        ox = jitter_x
        oy = -20.0 + jitter_y
        effects["accent"] = "shock_flash"

    elif action == "walking":
        # Stepped lateral sway + vertical bounce
        step_phase = (t * 2.2) % 1.0
        oy = -30.0 * abs(math.sin(step_phase * math.pi))
        ox = math.sin(t * 2.2 * math.pi) * 35.0
        rot = math.sin(t * 2.2 * math.pi) * 3.0

    elif action == "sitting":
        # Anchored lower-third, subtle breathing
        oy = 60.0 + math.sin(cycle * 0.6) * 4.0
        sy = 0.96 + math.sin(cycle * 0.6) * 0.01

    elif action == "reacting":
        # Quick snap turn + zoom focus
        enter = min(1.0, t / 0.3)
        rot = (1.0 - enter) * -15.0
        sx = 1.0 + 0.08 * enter
        sy = 1.0 + 0.08 * enter
        oy = -15.0 * enter

    elif action == "celebrating":
        # Upbeat double-bounce with rotation swing
        bounce = abs(math.sin(t * 4.0 * math.pi))
        oy = -55.0 * bounce
        sy = 1.05 + 0.06 * bounce
        rot = math.sin(t * 3.0 * math.pi) * 4.0
        effects["accent"] = "confetti"

    elif action == "frustrated":
        # Rapid head shake and tension pulse
        shake = math.sin(t * 18.0 * math.pi) * 10.0
        ox = shake
        sy = 1.02 + 0.03 * math.sin(t * 8.0 * math.pi)
        effects["accent"] = "steam_puff"

    elif action == "explaining":
        # Conversational forward lean with alternating hand rhythm
        lean = math.sin(cycle * 0.9)
        oy = -15.0 + lean * 8.0
        rot = math.sin(cycle * 0.45) * 2.5
        sy = 1.01 + lean * 0.02
        effects["gesture"] = "explain_hands"

    elif action == "holding_object":
        # Subtle presentation breathing with prop held firmly
        breathe = math.sin(cycle * 0.7) * 0.015
        sy = 1.0 + breathe
        oy = math.sin(cycle * 0.7) * 6.0
        effects["prop"] = True

    return sx, sy, ox, oy, rot, alpha, effects


# ------------------------------------------------------------- Frame Rendering
def draw_prop_overlay(frame: np.ndarray, prop: str, x: int, y: int, scale: float):
    """Draw a clean vector/icon prop on the character."""
    p = (prop or "card").lower()
    h, w = frame.shape[:2]
    s = int(scale * 60)

    if p == "phone":
        pw, ph = int(s * 0.6), int(s * 1.1)
        cv2.rectangle(frame, (x - pw // 2, y - ph // 2), (x + pw // 2, y + ph // 2), (30, 30, 35), -1)
        cv2.rectangle(frame, (x - pw // 2, y - ph // 2), (x + pw // 2, y + ph // 2), (180, 180, 190), 2)
        cv2.rectangle(frame, (x - pw // 2 + 4, y - ph // 2 + 6), (x + pw // 2 - 4, y + ph // 2 - 8), (220, 240, 255), -1)

    elif p == "card":
        pw, ph = int(s * 1.2), int(s * 0.8)
        cv2.rectangle(frame, (x - pw // 2, y - ph // 2), (x + pw // 2, y + ph // 2), (45, 140, 240), -1)
        cv2.rectangle(frame, (x - pw // 2, y - ph // 2), (x + pw // 2, y + ph // 2), (255, 255, 255), 2)
        cv2.line(frame, (x - pw // 2 + 8, y), (x + pw // 2 - 8, y), (255, 255, 255), 2)

    elif p in ("pointer", "magnifier"):
        rad = int(s * 0.45)
        cv2.circle(frame, (x, y - rad // 2), rad, (220, 240, 255), -1)
        cv2.circle(frame, (x, y - rad // 2), rad, (40, 40, 45), 3)
        cv2.line(frame, (x + int(rad * 0.7), y - rad // 2 + int(rad * 0.7)),
                 (x + int(rad * 1.5), y - rad // 2 + int(rad * 1.5)), (60, 60, 70), 5)

    elif p == "trophy":
        rad = int(s * 0.5)
        cv2.circle(frame, (x, y - rad), rad, (0, 215, 255), -1)
        cv2.rectangle(frame, (x - rad // 3, y - rad // 2), (x + rad // 3, y + rad // 2), (0, 180, 220), -1)
        cv2.rectangle(frame, (x - rad // 2, y + rad // 2), (x + rad // 2, y + rad), (40, 40, 50), -1)

    else: # document / book
        pw, ph = int(s * 0.9), int(s * 1.2)
        cv2.rectangle(frame, (x - pw // 2, y - ph // 2), (x + pw // 2, y + ph // 2), (245, 245, 250), -1)
        cv2.rectangle(frame, (x - pw // 2, y - ph // 2), (x + pw // 2, y + ph // 2), (80, 80, 90), 2)
        for ly in range(y - ph // 3, y + ph // 3, max(6, ph // 5)):
            cv2.line(frame, (x - pw // 3, ly), (x + pw // 3, ly), (140, 140, 150), 2)


def render_action_frame(base_bg: np.ndarray, character_rgba: np.ndarray,
                        action: str, t: float, duration: float,
                        prop: str | None = None, pulse_level: float = 0.0) -> np.ndarray:
    """Composite a single frame of the character performing their action."""
    frame = base_bg.copy()
    h, w = frame.shape[:2]

    # Compute transform
    sx, sy, ox, oy, rot, alpha, effects = compute_action_transform(
        action, t, duration, has_audio_pulse=(pulse_level > 0.01), pulse_level=pulse_level
    )

    # Base positioning: character anchored horizontally centered, upper-mid frame
    # Leaving safe lower-third for subtitles and platform UI
    char_h, char_w = character_rgba.shape[:2]
    target_h = int(h * 0.52 * sy)
    target_w = int(char_w * (target_h / char_h) * sx)
    target_w = max(10, target_w)
    target_h = max(10, target_h)

    resized_char = cv2.resize(character_rgba, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

    # Rotation
    if abs(rot) > 0.1:
        m_rot = cv2.getRotationMatrix2D((target_w // 2, target_h // 2), rot, 1.0)
        resized_char = cv2.warpAffine(resized_char, m_rot, (target_w, target_h), flags=cv2.INTER_LINEAR,
                                      borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))

    # Center position: upper-mid area (y ~ 0.48) to keep lower-third completely clear for captions
    cx = int(w * 0.5 + ox)
    cy = int(h * 0.48 + oy)
    x1 = cx - target_w // 2
    y1 = cy - target_h // 2
    x2 = x1 + target_w
    y2 = y1 + target_h

    # Clip bounds
    src_x1 = max(0, -x1)
    src_y1 = max(0, -y1)
    src_x2 = target_w - max(0, x2 - w)
    src_y2 = target_h - max(0, y2 - h)

    dst_x1 = max(0, x1)
    dst_y1 = max(0, y1)
    dst_x2 = min(w, x2)
    dst_y2 = min(h, y2)

    if dst_x2 > dst_x1 and dst_y2 > dst_y1 and src_x2 > src_x1 and src_y2 > src_y1:
        patch_char = resized_char[src_y1:src_y2, src_x1:src_x2]
        char_bgr = patch_char[:, :, :3]
        char_a = (patch_char[:, :, 3].astype(np.float32) / 255.0) * alpha

        dst_roi = frame[dst_y1:dst_y2, dst_x1:dst_x2]
        for c in range(3):
            dst_roi[:, :, c] = (char_bgr[:, :, c] * char_a + dst_roi[:, :, c] * (1.0 - char_a)).astype(np.uint8)

    # Render prop overlay
    if prop or effects.get("prop"):
        p_name = prop or "card"
        prop_x = int(cx + (target_w * 0.28 if "right" in action else -target_w * 0.28))
        prop_y = int(cy + target_h * 0.05)
        draw_prop_overlay(frame, p_name, prop_x, prop_y, scale=float(target_h) / float(h))

    # Render expressive action accents
    accent = effects.get("accent")
    if accent == "question_mark":
        qx = int(cx + target_w * 0.28)
        qy = int(y1 + 40 + math.sin(t * 5.0) * 8.0)
        cv2.putText(frame, "?", (qx, qy), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (20, 20, 30), 8, cv2.LINE_AA)
        cv2.putText(frame, "?", (qx, qy), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (255, 220, 50), 4, cv2.LINE_AA)

    elif accent == "thought_bubble":
        bx = int(cx + target_w * 0.32)
        by = int(y1 + 30)
        cv2.circle(frame, (bx - 20, by + 20), 8, (240, 240, 250), -1)
        cv2.circle(frame, (bx - 10, by + 5), 14, (240, 240, 250), -1)
        cv2.circle(frame, (bx + 15, by - 15), 26, (240, 240, 250), -1)
        cv2.circle(frame, (bx + 15, by - 15), 26, (120, 130, 160), 2)

    elif accent == "shock_flash":
        if (int(t * 15.0) % 2) == 0:
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (w, h), (255, 255, 200), -1)
            cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)

    elif accent == "confetti":
        rng = np.random.default_rng(int(t * 8.0) * 31 + 7)
        for _ in range(16):
            px = int(rng.uniform(w * 0.1, w * 0.9))
            py = int(rng.uniform(h * 0.1, h * 0.6))
            col = (int(rng.integers(50, 255)), int(rng.integers(150, 255)), int(rng.integers(50, 255)))
            cv2.circle(frame, (px, py), int(rng.integers(4, 9)), col, -1)

    return frame


def render_character_action_clip(character_img_path: str, action: str,
                                 out_mp4: str, duration: float,
                                 width: int = 720, height: int = 1280,
                                 fps: int = 25, prop: str | None = None,
                                 audio_path: str | None = None) -> str:
    """Render a complete MP4 video of the character performing their action."""
    act = normalize_action(action)
    dur = max(0.5, float(duration))
    num_frames = int(round(dur * fps))

    # Read character asset
    default_asset = os.path.join(os.path.dirname(__file__), "assets", "character_default.png")
    if not character_img_path or not os.path.exists(character_img_path):
        if os.path.exists(default_asset):
            character_img_path = default_asset

    if not character_img_path or not os.path.exists(character_img_path):
        # Generate placeholder humanoid avatar
        char_rgba = np.zeros((600, 400, 4), dtype=np.uint8)
        # Face / head
        cv2.circle(char_rgba, (200, 180), 90, (230, 200, 180, 255), -1)
        # Eyes
        cv2.circle(char_rgba, (165, 170), 10, (40, 30, 30, 255), -1)
        cv2.circle(char_rgba, (235, 170), 10, (40, 30, 30, 255), -1)
        # Smile
        cv2.ellipse(char_rgba, (200, 210), (35, 20), 0, 0, 180, (40, 30, 30, 255), 4)
        # Body / shirt
        cv2.ellipse(char_rgba, (200, 450), (140, 200), 0, 0, 360, (60, 120, 220, 255), -1)
    else:
        raw = cv2.imread(character_img_path, cv2.IMREAD_UNCHANGED)
        if raw is None:
            char_rgba = np.zeros((600, 400, 4), dtype=np.uint8)
            cv2.circle(char_rgba, (200, 200), 120, (100, 180, 255, 255), -1)
        elif raw.shape[2] == 4:
            char_rgba = raw
        else:
            # Add alpha channel with soft ellipse mask
            char_bgr = raw
            h_c, w_c = char_bgr.shape[:2]
            alpha = np.zeros((h_c, w_c), dtype=np.uint8)
            cv2.ellipse(alpha, (w_c // 2, h_c // 2), (int(w_c * 0.44), int(h_c * 0.46)), 0, 0, 360, 255, -1)
            alpha = cv2.GaussianBlur(alpha, (25, 25), 0)
            char_rgba = np.dstack([char_bgr, alpha])

    # Generate studio background (sleek vertical backdrop with radial soft light)
    bg = np.zeros((height, width, 3), dtype=np.uint8)
    yy, xx = np.mgrid[0:height, 0:width]
    # Subtle dark studio gradient: deep slate top to dark charcoal bottom
    grad = (yy / float(height))
    bg[:, :, 0] = (22 + grad * 12).astype(np.uint8)
    bg[:, :, 1] = (26 + grad * 10).astype(np.uint8)
    bg[:, :, 2] = (34 + grad * 8).astype(np.uint8)

    # Studio soft spotlight in center
    spot = np.exp(-(((xx - width * 0.5) ** 2) / (2 * (width * 0.4) ** 2) +
                    ((yy - height * 0.55) ** 2) / (2 * (height * 0.4) ** 2)))
    for c, tint in enumerate([40, 50, 70]):
        bg[:, :, c] = np.clip(bg[:, :, c].astype(np.float32) + spot * tint, 0, 255).astype(np.uint8)

    # Floor grid / horizon guide (modern creative stage)
    horizon_y = int(height * 0.82)
    cv2.line(bg, (0, horizon_y), (width, horizon_y), (45, 52, 65), 2)

    # Render frames to pipe or temp directory
    tmp_avi = out_mp4 + ".tmp.avi"
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    vw = cv2.VideoWriter(tmp_avi, fourcc, fps, (width, height))

    try:
        for i in range(num_frames):
            t = float(i) / float(fps)
            frame = render_action_frame(bg, char_rgba, act, t, dur, prop=prop)
            vw.write(frame)
        vw.release()

        # Remux to standard H.264 MP4 with ffmpeg
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
