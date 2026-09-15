"""Render production video: Myth vs Fact (ជំនឿ និងការពិត).

Topic: 'តើការផឹកទឹកកកពេលក្តៅ ធ្វើឲ្យមិនស្រួលខ្លួនពិតមែនឬ?'
"""
import os
import subprocess
from ai_studio import captions as cap
from ai_studio import character_actions as ca
from ai_studio import config as cfg_mod
from ai_studio import media
from ai_studio import meme_engine as me
from ai_studio import qa
from ai_studio.engines import tts

# Anchored to the repo root so the output always lands in the folder the
# gallery serves (ai_studio/app.py mounts <repo>/outputs), even when this
# renderer is launched from another working directory.
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(REPO_ROOT, "outputs", "myth_vs_fact")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SCENES = [
    {
        "idx": 0,
        "title": "Hook",
        "text": "តើអ្នកធ្លាប់ឮចាស់ៗប្រាប់ថា ក្តៅខ្លាំងកុំផឹកទឹកកកអត់?",
        "action": "thinking",
        "prop": "none",
        "visual_source": "character_action",
        "emotion": "surprised",
    },
    {
        "idx": 1,
        "title": "Myth",
        "text": "ជំនឿទូទៅគិតថា ទឹកកកធ្វើឲ្យសីតុណ្ហភាពក្នុងខ្លួនប្រែប្រួលភ្លាមៗ ហើយធ្វើឲ្យយើងក្តៅខ្លួន ឬផ្តាសាយ។",
        "action": "confused",
        "prop": "none",
        "visual_source": "character_action",
        "emotion": "serious",
    },
    {
        "idx": 2,
        "title": "Fact",
        "text": "ប៉ុន្តែការពិតវេជ្ជសាស្ត្របញ្ជាក់ថា ទឹកកកមិនមែនជាមូលហេតុទេ។ ផ្តាសាយបង្កឡើងដោយវីរុស មិនមែនទឹកត្រជាក់ឡើយ!",
        "action": "explaining",
        "prop": "book",
        "visual_source": "character_action",
        "emotion": "strong",
    },
    {
        "idx": 3,
        "title": "Meme Reaction",
        "text": "តែរឿងពិតមួយទៀតគឺ... ផឹកលឿនពេក ឈឺក្បាលខ្ទោកៗ Brain Freeze ជារឿងពិត!",
        "action": "shocked",
        "prop": "none",
        "visual_source": "meme",
        "meme_type": "reaction_shock",
        "emotion": "excited",
    },
    {
        "idx": 4,
        "title": "Takeaway & CTA",
        "text": "ដូច្នេះអ្នកអាចផឹកបានធម្មតា គ្រាន់តែកុំផឹកបង្ខំពេក! ចុះអ្នកវិញ ចូលចិត្តទឹកកកឬទឹកក្តៅ? ខមិនមក!",
        "action": "pointing_down",
        "prop": "microphone",
        "visual_source": "character_action",
        "emotion": "happy",
    },
]


def render_myth_fact():
    cfg = cfg_mod.load()
    char_asset = os.path.join(REPO_ROOT, "ai_studio", "assets", "character_default.png")
    scene_clips = []
    ass_dialogues = []
    current_time = 0.0

    print("=== Step 1: Synthesizing Audio & Rendering Scene Clips ===")
    for s in SCENES:
        idx = s["idx"]
        text = s["text"]
        action = s["action"]
        emotion = s["emotion"]
        vs = s["visual_source"]

        # Validate script
        sc_check = qa.validate_khmer_script(text)
        assert sc_check["passed"], f"Script error in scene {idx}: {sc_check['issues']}"

        # 1. Audio
        audio_out = os.path.join(OUTPUT_DIR, f"scene_{idx}_audio.wav")
        res_tts = tts.synthesize(text, audio_out, cfg, emotion_style=emotion)
        assert res_tts["ok"]
        aud_check = qa.validate_voice_audio(audio_out)
        dur = max(2.5, aud_check["duration"])
        # Real measured length, so the QA gate checks pacing against the
        # audio it just made instead of its 3.0s placeholder default.
        s["audio_duration"] = dur
        s["estimated_duration_sec"] = dur

        # 2. Visual Clip
        video_out = os.path.join(OUTPUT_DIR, f"scene_{idx}_video.mp4")
        if vs == "meme":
            me.render_meme_clip(s["meme_type"], text[:28], video_out, dur, 720, 1280, 25)
        else:
            ca.render_character_action_clip(
                char_asset, action, video_out, dur, 720, 1280, 25,
                prop=s.get("prop"), audio_path=audio_out
            )

        # 3. Mux
        muxed_clip = os.path.join(OUTPUT_DIR, f"scene_{idx}_muxed.mp4")
        subprocess.check_call([
            "ffmpeg", "-y", "-i", video_out, "-i", audio_out,
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", muxed_clip
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        scene_clips.append(muxed_clip)
        ass_dialogues.append((current_time + 0.1, current_time + dur - 0.1, text))
        current_time += dur
        print(f"  ✓ Scene {idx + 1} ({s['title']}): {dur:.2f}s [{action}] [{emotion}]")

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

    print("\n=== Step 3: Burning Subtitles via HarfBuzz ASS Shaper ===")
    ass_path = os.path.join(OUTPUT_DIR, "subtitles.ass")
    st, _ = cap.validate_style({"preset": "clean"})
    cap.build_ass(ass_dialogues, st, 720, 1280, ass_path)

    final_mp4 = os.path.join(OUTPUT_DIR, "Myth_vs_Fact_Final.mp4")
    media.burn_ass(assembled_raw, ass_path, final_mp4)
    print(f"  ✓ Final video produced: {final_mp4} ({os.path.getsize(final_mp4)} bytes)")

    print("\n=== Step 4: Extracting Inspection Frames ===")
    frames = [
        ("frame_hook.png", 1.5),
        ("frame_myth.png", 5.5),
        ("frame_fact.png", 12.0),
        ("frame_meme.png", 18.0),
        ("frame_cta.png", 23.0),
    ]
    for fname, t_sec in frames:
        fpath = os.path.join(OUTPUT_DIR, fname)
        subprocess.check_call([
            "ffmpeg", "-y", "-ss", str(t_sec), "-i", final_mp4,
            "-vframes", "1", fpath
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"  ✓ Extracted {fname} at {t_sec}s")

    print("\n=== Step 5: Running QA Gate Verification ===")
    full_qa = qa.run_full_project_qa(SCENES, final_mp4_path=final_mp4, content_type="myth_vs_fact")
    print("  QA Gate Approved:", full_qa["approved"])
    print("  Failures:", full_qa["failures"])
    print("  Warnings:", full_qa["warnings"])
    print("  MP4 Verified:", full_qa["mp4_verified"])
    assert full_qa["approved"]
    assert full_qa["mp4_verified"]

    return final_mp4


if __name__ == "__main__":
    render_myth_fact()
