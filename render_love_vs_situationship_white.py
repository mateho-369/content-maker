#!/usr/bin/env python3
"""Render Love vs Situationship on Clean White Studio Background.

Features:
- Clean white studio background (9:16 vertical 720x1280).
- Real internet example photos for Real Love and Situationship.
- Reusable cute character mascot (Kiri) performing animated explaining actions.
- Natural Khmer audio synthesized via free TTS pipeline with emotional shaper.
- Khmer ASS subtitles with HarfBuzz shaping in high-contrast soft card panel.
- Full QA verification and integration into live gallery preview.
"""

import os
import subprocess
import cv2
import numpy as np

from ai_studio import character_actions as ca
from ai_studio import captions as cap
from ai_studio import media
from ai_studio import qa
from ai_studio import config as cfg_mod
from ai_studio.engines import tts

OUTPUT_DIR = "outputs/love_vs_situationship_white"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Internet example images
IMG_REAL_LOVE = "image-search/happy-couple-walking-together-sunset-rom-1.jpg"
IMG_SITUATIONSHIP = "image-search/person-looking-at-phone-alone-night-sad--1.jpg"

SCENES = [
    {
        "idx": 0,
        "title": "Hook: Real Love vs Situationship",
        "text": "តើអ្នកកំពុងមាន Real Love ឬគ្រាន់តែជា Situationship? តោះមកមើលទាំងអស់គ្នា!",
        "action": "thinking",
        "prop": "none",
        "emotion": "surprised",
        "has_example_img": False,
        "example_img": None,
        "example_badge": None,
    },
    {
        "idx": 1,
        "title": "Real Love (ស្នេហាពិត)",
        "text": "Real Love គឺការស្រឡាញ់ច្បាស់លាស់ ផ្ដល់តម្លៃ យកចិត្តទុកដាក់ និងរួមដំណើរជាមួយគ្នាជានិច្ច!",
        "action": "explaining",
        "prop": "none",
        "emotion": "happy",
        "has_example_img": True,
        "example_img": IMG_REAL_LOVE,
        "example_badge": "REAL LOVE 💖",
    },
    {
        "idx": 2,
        "title": "Situationship (ទំនាក់ទំនងអត់ឈ្មោះ)",
        "text": "រីឯ Situationship គឺអត់ច្បាស់លាស់ ផ្ញើសារតែពេលអផ្សុក ហើយទុកយើងត្រឹមតែជាជម្រើស!",
        "action": "confused",
        "prop": "none",
        "emotion": "sad",
        "has_example_img": True,
        "example_img": IMG_SITUATIONSHIP,
        "example_badge": "SITUATIONSHIP 🥀",
    },
    {
        "idx": 3,
        "title": "Reality Check Meme",
        "text": "ឈឺចាប់បំផុត គឺពេលដឹងថាខ្លួនឯងគ្រាន់តែជាជម្រើសពេលគេអផ្សុក... កុំចាញ់បោកគេណា!",
        "action": "shocked",
        "prop": "none",
        "emotion": "excited",
        "has_example_img": False,
        "example_img": None,
        "example_badge": None,
    },
    {
        "idx": 4,
        "title": "Summary Comparison",
        "text": "សរុបមក Real Love ផ្ដល់ភាពកក់ក្តៅ រីឯ Situationship ផ្ដល់តែភាពស្រពេចស្រពិល និងខាតពេលវេលា!",
        "action": "explaining",
        "prop": "book",
        "emotion": "storytelling",
        "has_example_img": False,
        "example_img": None,
        "example_badge": None,
    },
    {
        "idx": 5,
        "title": "Ending & CTA",
        "text": "ជ្រើសរើសមនុស្សដែលឱ្យតម្លៃអ្នក! ចុះទំនាក់ទំនងរបស់អ្នកវិញ ស្ថិតក្នុងចំណុចមួយណា? ខមិនមក!",
        "action": "pointing_down",
        "prop": "microphone",
        "emotion": "happy",
        "has_example_img": False,
        "example_img": None,
        "example_badge": None,
    },
]


def create_white_background(width: int = 720, height: int = 1280, example_img_path: str | None = None, badge_text: str | None = None) -> np.ndarray:
    """Create a modern white studio background with optional floating photo card."""
    bg = np.ones((height, width, 3), dtype=np.uint8) * 255
    yy, xx = np.mgrid[0:height, 0:width]
    grad = (yy / float(height))
    # Soft modern light slate tint
    bg[:, :, 0] = np.clip(250 - grad * 10, 0, 255).astype(np.uint8)
    bg[:, :, 1] = np.clip(252 - grad * 8, 0, 255).astype(np.uint8)
    bg[:, :, 2] = np.clip(255 - grad * 5, 0, 255).astype(np.uint8)

    # Floor horizon line
    horizon_y = int(height * 0.82)
    cv2.line(bg, (0, horizon_y), (width, horizon_y), (225, 230, 240), 2)

    # If internet example image is provided, draw floating card at upper portion
    if example_img_path and os.path.exists(example_img_path):
        card_w, card_h = 600, 340
        card_x1 = (width - card_w) // 2
        card_y1 = 80
        card_x2 = card_x1 + card_w
        card_y2 = card_y1 + card_h

        ex_img = cv2.imread(example_img_path)
        if ex_img is not None:
            ih, iw = ex_img.shape[:2]
            scale = max(card_w / iw, card_h / ih)
            rw, rh = int(iw * scale), int(ih * scale)
            ex_resized = cv2.resize(ex_img, (rw, rh), interpolation=cv2.INTER_AREA)
            cx, cy = (rw - card_w) // 2, (rh - card_h) // 2
            crop = ex_resized[cy:cy+card_h, cx:cx+card_w]

            # Soft drop shadow
            shadow = bg.copy()
            cv2.rectangle(shadow, (card_x1 - 6, card_y1 - 2), (card_x2 + 6, card_y2 + 12), (210, 215, 225), -1)
            bg = cv2.addWeighted(shadow, 0.45, bg, 0.55, 0)

            # Draw image content
            bg[card_y1:card_y2, card_x1:card_x2] = crop
            # Outer white border & inner clean line
            cv2.rectangle(bg, (card_x1, card_y1), (card_x2, card_y2), (255, 255, 255), 4)
            cv2.rectangle(bg, (card_x1, card_y1), (card_x2, card_y2), (200, 205, 215), 2)

            # Badge overlay
            if badge_text:
                clean_badge = badge_text.split(" ")[0] + (" " + badge_text.split(" ")[1] if len(badge_text.split(" ")) > 1 else "")
                cv2.rectangle(bg, (card_x1 + 16, card_y1 + 16), (card_x1 + 240, card_y1 + 54), (20, 25, 35), -1)
                cv2.putText(bg, clean_badge, (card_x1 + 24, card_y1 + 42), cv2.FONT_HERSHEY_DUPLEX, 0.72, (255, 255, 255), 2, cv2.LINE_AA)

    return bg


def render_white_scene_clip(character_img_path: str, action: str, out_mp4: str,
                            duration: float, width: int = 720, height: int = 1280,
                            fps: int = 25, prop: str | None = None,
                            example_img_path: str | None = None,
                            badge_text: str | None = None) -> str:
    """Render one scene clip with white background, optional example photo, and animated mascot."""
    act = ca.normalize_action(action)
    dur = max(0.5, float(duration))
    num_frames = int(round(dur * fps))

    char_rgba = cv2.imread(character_img_path, cv2.IMREAD_UNCHANGED)
    if char_rgba is None:
        raise ValueError(f"Cannot load character asset: {character_img_path}")

    base_bg = create_white_background(width, height, example_img_path, badge_text)

    tmp_avi = out_mp4 + ".tmp.avi"
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    vw = cv2.VideoWriter(tmp_avi, fourcc, fps, (width, height))

    try:
        for i in range(num_frames):
            t = float(i) / float(fps)
            frame = ca.render_action_frame(base_bg, char_rgba, act, t, dur, prop=prop)
            vw.write(frame)
        vw.release()

        # Remux to standard H.264 MP4
        cmd = [
            "ffmpeg", "-y", "-i", tmp_avi,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-pix_fmt", "yuv420p", out_mp4
        ]
        subprocess.run(cmd, check=True, capture_output=True)
    finally:
        if os.path.exists(tmp_avi):
            try:
                os.remove(tmp_avi)
            except OSError:
                pass

    return out_mp4


def render_project():
    cfg = cfg_mod.load()
    char_asset = "ai_studio/assets/character_default.png"
    scene_clips = []
    ass_dialogues = []
    current_time = 0.0

    print("=== Step 1: Synthesizing Audio & Rendering Scene Clips (White Studio) ===")
    for s in SCENES:
        idx = s["idx"]
        text = s["text"]
        action = s["action"]
        emotion = s["emotion"]
        ex_img = s["example_img"]
        badge = s["example_badge"]

        # 1. Synthesize audio
        audio_out = os.path.join(OUTPUT_DIR, f"scene_{idx}_audio.wav")
        res_tts = tts.synthesize(text, audio_out, cfg, emotion_style=emotion)
        dur = float(res_tts.get("duration", 5.0))
        aud_check = qa.validate_voice_audio(audio_out)
        if not aud_check.get("passed", True):
            print(f"  [Warning] Audio check: {aud_check.get('issues')}")

        # 2. Render scene video with white background and internet example image
        video_out = os.path.join(OUTPUT_DIR, f"scene_{idx}_video.mp4")
        render_white_scene_clip(
            char_asset, action, video_out, dur,
            width=720, height=1280, fps=25,
            prop=s.get("prop"),
            example_img_path=ex_img,
            badge_text=badge
        )

        # 3. Combine audio + video
        muxed_out = os.path.join(OUTPUT_DIR, f"scene_{idx}_muxed.mp4")
        cmd_mux = [
            "ffmpeg", "-y", "-i", video_out, "-i", audio_out,
            "-c:v", "copy", "-c:a", "aac", "-shortest", muxed_out
        ]
        subprocess.run(cmd_mux, check=True, capture_output=True)
        scene_clips.append(muxed_out)

        # Dialogue segment for ASS subtitles
        ass_dialogues.append((current_time, current_time + dur, text))
        current_time += dur

        print(f"  ✓ Scene {idx + 1} ({s['title']}): {dur:.2f}s [{action}] [{emotion}] [Img: {bool(ex_img)}]")

    print(f"\n=== Step 2: Concatenating {len(scene_clips)} Scenes ===")
    concat_list = os.path.join(OUTPUT_DIR, "concat_list.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        for clip in scene_clips:
            f.write(f"file '{os.path.abspath(clip)}'\n")

    assembled_raw = os.path.join(OUTPUT_DIR, "assembled_raw.mp4")
    subprocess.check_call([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", assembled_raw
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("\n=== Step 3: Burning Subtitles via HarfBuzz ASS Shaper (High-Contrast Soft Card) ===")
    ass_path = os.path.join(OUTPUT_DIR, "subtitles.ass")
    st, _ = cap.validate_style({
        "preset": "soft_card",
        "font": "kantumruy_pro",
        "weight": "bold",
        "text_color": "#ffffff",
        "panel": {
            "enabled": True,
            "color": "#0f172a",
            "opacity": 0.82,
            "padding_px": 14,
            "radius_px": 12
        }
    })
    cap.build_ass(ass_dialogues, st, 720, 1280, ass_path)

    final_mp4 = os.path.join(OUTPUT_DIR, "Love_vs_Situationship_White_Final.mp4")
    media.burn_ass(assembled_raw, ass_path, final_mp4)
    print(f"  ✓ Final video produced: {final_mp4} ({os.path.getsize(final_mp4)} bytes)")

    print("\n=== Step 4: Extracting Inspection Frames ===")
    frames = [
        ("frame_hook.png", 1.5),
        ("frame_real_love.png", 6.5),
        ("frame_situationship.png", 13.5),
        ("frame_meme.png", 20.0),
        ("frame_summary.png", 26.0),
        ("frame_cta.png", 32.0),
    ]
    for fname, t_sec in frames:
        fpath = os.path.join(OUTPUT_DIR, fname)
        subprocess.check_call([
            "ffmpeg", "-y", "-ss", str(t_sec), "-i", final_mp4,
            "-vframes", "1", fpath
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"  ✓ Extracted {fname} at {t_sec}s")

    print("\n=== Step 5: Running QA Gate Verification ===")
    full_qa = qa.run_full_project_qa(SCENES, final_mp4_path=final_mp4, content_type="compare")
    print("  QA Gate Approved:", full_qa["approved"])
    print("  Failures:", full_qa["failures"])
    print("  Warnings:", full_qa["warnings"])
    print("  MP4 Verified:", full_qa["mp4_verified"])


if __name__ == "__main__":
    render_project()
