#!/usr/bin/env python3
"""Render Love vs Situationship comparison video with:
- Clean white studio background
- Internet example photos for every single scene
- Reusable cute mascot character Kiri with actions
- Khmer speech synthesis (free API / offline pipeline)
- Khmer subtitles with 100% correct coeng subscripts
"""
import os
import subprocess
import cv2
import numpy as np

from ai_studio import character_actions as ca
from ai_studio.tts_providers import synthesize_speech
from ai_studio.qa import run_full_project_qa
from ai_studio.util import ffmpeg_exe
import khmercut

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "outputs", "love_vs_situationship_white_bg")
os.makedirs(OUT_DIR, exist_ok=True)

IMG_LOVE = os.path.join(ROOT, "image-search", "happy-couple-holding-hands-romantic-date-1.jpg")
IMG_SIT = os.path.join(ROOT, "image-search", "person-looking-at-phone-confused-sad-mix-1.jpg")
IMG_MEME = os.path.join(ROOT, "image-search", "funny-overthinking-headache-meme-reactio-2.jpg")
IMG_CTA = os.path.join(ROOT, "image-search", "happy-peaceful-person-walking-forward-co-1.jpg")

SCENES = [
    {
        "id": "hook",
        "action": "thinking",
        "emotion": "surprised",
        "script": "តើអ្នកធ្លាប់ឆ្ងល់អត់ថា ទំនាក់ទំនងរបស់អ្នកឥឡូវនេះ ជា Real Love ឬគ្រាន់តែជា Situationship?",
        "card_type": "split",
        "img_left": IMG_LOVE,
        "img_right": IMG_SIT,
        "badge_left": "REAL LOVE",
        "badge_right": "SITUATIONSHIP",
    },
    {
        "id": "real_love",
        "action": "pointing_left",
        "emotion": "happy",
        "script": "បើជា Real Love គេតែងតែផ្តល់ភាពច្បាស់លាស់ ឱ្យតម្លៃ និងមានគម្រោងអនាគតជាមួយអ្នកជានិច្ច!",
        "card_type": "single",
        "image_path": IMG_LOVE,
        "badge_text": "REAL LOVE EXAMPLE",
        "badge_color": (34, 139, 34),
    },
    {
        "id": "situationship",
        "action": "pointing_right",
        "emotion": "serious",
        "script": "ចំណែក Situationship វិញ គឺផ្ញើសាររាល់ថ្ងៃ តែគ្មានឈ្មោះ ពេលត្រូវការទើបនឹកឃើញ ធ្វើឱ្យអ្នកសង្ស័យខ្លួនឯង!",
        "card_type": "single",
        "image_path": IMG_SIT,
        "badge_text": "SITUATIONSHIP EXAMPLE",
        "badge_color": (30, 100, 220),
    },
    {
        "id": "meme",
        "action": "shocked",
        "emotion": "excited",
        "script": "តើត្រូវហៅថាមិត្តភក្តិ ឬសង្សារ? និយាយត្រង់ៗទៅ ឈឺក្បាលជាងរៀនគណិតវិទ្យាទៀត!",
        "card_type": "single",
        "image_path": IMG_MEME,
        "badge_text": "OVERTHINKING MEME",
        "badge_color": (220, 120, 20),
    },
    {
        "id": "cta",
        "action": "pointing_down",
        "emotion": "happy",
        "script": "កុំខ្ជះខ្ជាយពេលវេលាលើមនុស្សមិនច្បាស់លាស់! ចុះអ្នកវិញ ធ្លាប់ជួបរឿងនេះអត់? ខមិនប្រាប់មក!",
        "card_type": "single",
        "image_path": IMG_CTA,
        "badge_text": "CHOOSE REAL VALUE",
        "badge_color": (160, 50, 220),
    },
]


def create_white_studio_bg(width=720, height=1280):
    """Generate clean modern white studio backdrop with subtle radial falloff."""
    bg = np.full((height, width, 3), 253, dtype=np.uint8)
    yy, xx = np.mgrid[0:height, 0:width]
    dist = np.sqrt(((xx - width * 0.5) / (width * 0.6)) ** 2 + ((yy - height * 0.4) / (height * 0.6)) ** 2)
    light = np.clip(1.0 - 0.04 * dist, 0.94, 1.0)
    for c in range(3):
        bg[:, :, c] = np.clip(bg[:, :, c].astype(np.float32) * light, 0, 255).astype(np.uint8)
    return bg


def draw_card(bg, scene_cfg, width=720):
    """Draw upper visual card with internet pictures."""
    card_w = 560
    card_h = 320
    card_x = (width - card_w) // 2
    card_y = 85

    card_type = scene_cfg.get("card_type")
    if card_type == "split":
        # Left and Right comparison card
        img1 = cv2.imread(scene_cfg["img_left"])
        img2 = cv2.imread(scene_cfg["img_right"])
        if img1 is not None and img2 is not None:
            half_w = card_w // 2
            # Resize & crop left
            h1, w1 = img1.shape[:2]
            s1 = max(half_w / w1, card_h / h1)
            r1 = cv2.resize(img1, (int(w1 * s1), int(h1 * s1)), interpolation=cv2.INTER_AREA)
            crop1 = r1[(r1.shape[0] - card_h) // 2:(r1.shape[0] - card_h) // 2 + card_h,
                       (r1.shape[1] - half_w) // 2:(r1.shape[1] - half_w) // 2 + half_w]

            # Resize & crop right
            h2, w2 = img2.shape[:2]
            s2 = max(half_w / w2, card_h / h2)
            r2 = cv2.resize(img2, (int(w2 * s2), int(h2 * s2)), interpolation=cv2.INTER_AREA)
            crop2 = r2[(r2.shape[0] - card_h) // 2:(r2.shape[0] - card_h) // 2 + card_h,
                       (r2.shape[1] - half_w) // 2:(r2.shape[1] - half_w) // 2 + half_w]

            split_card = np.zeros((card_h, card_w, 3), dtype=np.uint8)
            split_card[:, :half_w] = crop1
            split_card[:, half_w:] = crop2

            # Shadow
            cv2.rectangle(bg, (card_x + 6, card_y + 8), (card_x + card_w + 6, card_y + card_h + 8), (218, 222, 230), -1)
            # Card
            bg[card_y:card_y + card_h, card_x:card_x + card_w] = split_card
            # Center divider
            cv2.line(bg, (card_x + half_w, card_y), (card_x + half_w, card_y + card_h), (255, 255, 255), 4)
            # Border
            cv2.rectangle(bg, (card_x, card_y), (card_x + card_w, card_y + card_h), (255, 255, 255), 4)
            cv2.rectangle(bg, (card_x, card_y), (card_x + card_w, card_y + card_h), (200, 206, 216), 2)

            # VS Circle
            cv2.circle(bg, (card_x + half_w, card_y + card_h // 2), 34, (255, 255, 255), -1)
            cv2.circle(bg, (card_x + half_w, card_y + card_h // 2), 30, (30, 40, 220), -1)
            cv2.putText(bg, "VS", (card_x + half_w - 20, card_y + card_h // 2 + 10), cv2.FONT_HERSHEY_DUPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)

            # Badges
            cv2.rectangle(bg, (card_x + 12, card_y + 12), (card_x + 12 + 160, card_y + 12 + 36), (34, 139, 34), -1)
            cv2.putText(bg, "REAL LOVE", (card_x + 22, card_y + 37), cv2.FONT_HERSHEY_DUPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

            cv2.rectangle(bg, (card_x + card_w - 12 - 190, card_y + 12), (card_x + card_w - 12, card_y + 12 + 36), (30, 100, 220), -1)
            cv2.putText(bg, "SITUATIONSHIP", (card_x + card_w - 12 - 180, card_y + 37), cv2.FONT_HERSHEY_DUPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
            return

    elif card_type == "single":
        img_p = scene_cfg.get("image_path", "")
        if os.path.exists(img_p):
            img = cv2.imread(img_p)
            if img is not None:
                h_i, w_i = img.shape[:2]
                scale = max(card_w / w_i, card_h / h_i)
                nw, nh = int(w_i * scale), int(h_i * scale)
                resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
                x_crop = (nw - card_w) // 2
                y_crop = (nh - card_h) // 2
                cropped = resized[y_crop:y_crop + card_h, x_crop:x_crop + card_w]

                # Soft drop shadow
                cv2.rectangle(bg, (card_x + 6, card_y + 8), (card_x + card_w + 6, card_y + card_h + 8), (218, 222, 230), -1)
                # Photo
                bg[card_y:card_y + card_h, card_x:card_x + card_w] = cropped
                # Border
                cv2.rectangle(bg, (card_x, card_y), (card_x + card_w, card_y + card_h), (255, 255, 255), 4)
                cv2.rectangle(bg, (card_x, card_y), (card_x + card_w, card_y + card_h), (200, 206, 216), 2)

                # Badge
                badge_text = scene_cfg.get("badge_text", "EXAMPLE")
                badge_color = scene_cfg.get("badge_color", (34, 139, 34))
                badge_w = 240
                badge_h = 40
                cv2.rectangle(bg, (card_x + 16, card_y + 16), (card_x + 16 + badge_w, card_y + 16 + badge_h), badge_color, -1)
                cv2.rectangle(bg, (card_x + 16, card_y + 16), (card_x + 16 + badge_w, card_y + 16 + badge_h), (255, 255, 255), 2)
                cv2.putText(bg, badge_text, (card_x + 24, card_y + 44), cv2.FONT_HERSHEY_DUPLEX, 0.52, (255, 255, 255), 1, cv2.LINE_AA)


def render_scene_clip(scene_cfg, index, char_rgba, ffmpeg_bin):
    """Render a single scene clip with audio, white background, internet photo card, and character."""
    print(f"  -> Rendering Scene {index + 1}: {scene_cfg['id']} [{scene_cfg['action']}] [{scene_cfg['emotion']}]")
    audio_path = os.path.join(OUT_DIR, f"scene_{index}_audio.wav")
    synthesize_speech(
        text=scene_cfg["script"],
        out_wav=audio_path,
        cfg={},
        emotion=scene_cfg["emotion"],
    )

    # Get duration
    dur_cmd = [ffmpeg_bin, "-i", audio_path]
    res = subprocess.run(dur_cmd, stderr=subprocess.PIPE, text=True)
    import re
    dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
    if dur_match:
        dur = float(dur_match.group(1)) * 3600 + float(dur_match.group(2)) * 60 + float(dur_match.group(3))
    else:
        dur = 5.0
    dur = max(3.0, dur + 0.3)

    width, height, fps = 720, 1280, 25
    num_frames = int(round(dur * fps))

    # Base background + visual card
    base_bg = create_white_studio_bg(width, height)
    draw_card(base_bg, scene_cfg, width)

    tmp_avi = os.path.join(OUT_DIR, f"scene_{index}_video.avi")
    vw = cv2.VideoWriter(tmp_avi, cv2.VideoWriter_fourcc(*"MJPG"), fps, (width, height))

    cy_ratio = 0.58
    char_scale = 0.46

    for f_idx in range(num_frames):
        t = float(f_idx) / float(fps)
        frame = base_bg.copy()
        sx, sy, ox, oy, rot, alpha, effects = ca.compute_action_transform(scene_cfg["action"], t, dur)
        char_h, char_w = char_rgba.shape[:2]
        target_h = int(height * char_scale * sy)
        target_w = int(char_w * (target_h / char_h) * sx)
        resized_char = cv2.resize(char_rgba, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

        if abs(rot) > 0.1:
            m_rot = cv2.getRotationMatrix2D((target_w // 2, target_h // 2), rot, 1.0)
            resized_char = cv2.warpAffine(resized_char, m_rot, (target_w, target_h),
                                          flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                                          borderValue=(0, 0, 0, 0))

        cx = int(width * 0.5 + ox)
        cy = int(height * cy_ratio + oy)
        x1, y1 = cx - target_w // 2, cy - target_h // 2
        x2, y2 = x1 + target_w, y1 + target_h

        src_x1, src_y1 = max(0, -x1), max(0, -y1)
        src_y2 = target_h - max(0, y2 - height)
        src_x2 = target_w - max(0, x2 - width)

        dst_x1, dst_y1 = max(0, x1), max(0, y1)
        dst_x2, dst_y2 = min(width, x2), min(height, y2)

        if dst_x2 > dst_x1 and dst_y2 > dst_y1 and src_x2 > src_x1 and src_y2 > src_y1:
            patch = resized_char[src_y1:src_y2, src_x1:src_x2]
            char_bgr = patch[:, :, :3]
            char_a = (patch[:, :, 3].astype(np.float32) / 255.0) * alpha
            roi = frame[dst_y1:dst_y2, dst_x1:dst_x2]
            for c in range(3):
                roi[:, :, c] = (char_bgr[:, :, c] * char_a + roi[:, :, c] * (1.0 - char_a)).astype(np.uint8)

        # Soft shadow under feet
        cv2.ellipse(frame, (width // 2, cy + target_h // 2 - 8), (int(target_w * 0.28), 12), 0, 0, 360, (215, 220, 228), -1)

        accent = effects.get("accent")
        if accent == "question_mark":
            cv2.putText(frame, "?", (cx + int(target_w * 0.25), y1 + 30), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (230, 80, 50), 3, cv2.LINE_AA)
        elif accent == "sweat_drops":
            cv2.circle(frame, (cx + int(target_w * 0.26), y1 + 30), 8, (240, 150, 40), -1)

        vw.write(frame)
    vw.release()

    muxed_mp4 = os.path.join(OUT_DIR, f"scene_{index}_muxed.mp4")
    cmd = [
        ffmpeg_bin, "-y",
        "-i", tmp_avi,
        "-i", audio_path,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        muxed_mp4
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    if os.path.exists(tmp_avi):
        os.remove(tmp_avi)

    return muxed_mp4, dur


def build_ass_subtitles(scenes_durations):
    """Generate ASS subtitles with HarfBuzz styling & dark pill contrast on white background."""
    ass_path = os.path.join(OUT_DIR, "subtitles.ass")
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 720",
        "PlayResY: 1280",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: KhmerWhiteBG,Kantumruy Pro,42,&H00FFFFFF,&H000000FF,&H00000000,&HE6161B26,1,0,0,0,100,100,0,0,3,10,10,2,40,40,90,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    def fmt_time(secs):
        h = int(secs // 3600)
        m = int((secs % 3600) // 60)
        s = secs % 60
        return f"{h:01d}:{m:02d}:{s:05.2f}"

    cur_time = 0.0
    for scene, dur in scenes_durations:
        start_str = fmt_time(cur_time + 0.1)
        end_str = fmt_time(cur_time + dur - 0.1)
        text = scene["script"]

        # Word wrap with khmercut
        tokens = khmercut.tokenize(text)
        if len(text) > 35 and len(tokens) > 4:
            mid = len(tokens) // 2
            text = "".join(tokens[:mid]) + "\\N" + "".join(tokens[mid:])

        lines.append(f"Dialogue: 0,{start_str},{end_str},KhmerWhiteBG,,0,0,0,,{text}")
        cur_time += dur

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return ass_path


def render_full_production():
    print("=== Step 1: Synthesizing & Rendering White Background Scene Clips ===")
    ffmpeg_bin = ffmpeg_exe()
    char_path = os.path.join(ROOT, "ai_studio", "assets", "character_default.png")
    char_rgba = cv2.imread(char_path, cv2.IMREAD_UNCHANGED)

    scene_clips = []
    scenes_durations = []
    for i, scene in enumerate(SCENES):
        clip_path, dur = render_scene_clip(scene, i, char_rgba, ffmpeg_bin)
        scene_clips.append(clip_path)
        scenes_durations.append((scene, dur))

    print("\n=== Step 2: Concatenating Scenes ===")
    concat_txt = os.path.join(OUT_DIR, "concat_list.txt")
    with open(concat_txt, "w") as f:
        for c in scene_clips:
            f.write(f"file '{os.path.basename(c)}'\n")

    raw_mp4 = os.path.join(OUT_DIR, "assembled_raw.mp4")
    concat_cmd = [
        ffmpeg_bin, "-y", "-f", "concat", "-safe", "0",
        "-i", concat_txt,
        "-c", "copy", raw_mp4
    ]
    subprocess.run(concat_cmd, cwd=OUT_DIR, check=True, capture_output=True)

    print("\n=== Step 3: Burning Khmer Subtitles ===")
    ass_path = build_ass_subtitles(scenes_durations)
    fonts_dir = os.path.join(ROOT, "ai_studio", "assets", "fonts")

    final_mp4 = os.path.join(OUT_DIR, "Love_vs_Situationship_WhiteBG.mp4")
    burn_cmd = [
        ffmpeg_bin, "-y",
        "-i", raw_mp4,
        "-vf", f"ass={ass_path}:fontsdir={fonts_dir}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        final_mp4
    ]
    subprocess.run(burn_cmd, check=True, capture_output=True)
    print(f"  ✓ Final video produced: {final_mp4} ({os.path.getsize(final_mp4)} bytes)")

    print("\n=== Step 4: Extracting Inspection Frames ===")
    t_inspect = [2.0, 10.0, 18.0, 26.0, 32.0]
    names = ["frame_hook.png", "frame_real_love.png", "frame_situationship.png", "frame_meme.png", "frame_cta.png"]
    for t_s, fname in zip(t_inspect, names):
        out_f = os.path.join(OUT_DIR, fname)
        cmd = [ffmpeg_bin, "-y", "-ss", str(t_s), "-i", final_mp4, "-vframes", "1", out_f]
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"  ✓ Extracted {fname} at {t_s}s")

    print("\n=== Step 5: Running QA Gate Verification ===")
    qa_report = run_full_project_qa(scenes=[{"text": s["script"]} for s in SCENES], final_mp4_path=final_mp4, content_type="compare")
    print(f"  QA Gate Approved: {qa_report['approved']}")
    print(f"  Failures: {qa_report['failures']}")
    print(f"  Warnings: {qa_report['warnings']}")
    print(f"  MP4 Verified: {qa_report['mp4_verified']}")


if __name__ == "__main__":
    render_full_production()
