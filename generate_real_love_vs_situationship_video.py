"""Render the required real content video: 'តើយើងកំពុងមាន Real Love ឬ Situationship?'

Structure:
1. Hook: 'តើអ្នកកំពុងស្រឡាញ់គេ... ឬកំពុងនៅក្នុង Situationship?' (surprised / questioning)
2. A: Real Love: 'ចំណុចទីមួយ បើជា Real Love គេតែងតែច្បាស់លាស់ យកចិត្តទុកដាក់ និងមិនដែលធ្វើឲ្យយើងឯកោឡើយ។' (happy / pointing left)
3. B: Situationship: 'តែបើជា Situationship វិញ ផ្ញើសារដូចសង្សារ តែពេលសួររឿងអនាគត គេថាសុំពេលគិតសិន!' (confused / pointing right)
4. Middle Meme: 'ឈឺចាប់បំផុត គឺពេលដឹងថាខ្លួនឯងគ្រាន់តែជាជម្រើសពេលគេអផ្សុក!' (reaction meme with comedic punch-in)
5. Summary: 'សរុបមក Real Love គឺភាពច្បាស់លាស់ រីឯ Situationship គឺភាពមិនច្បាស់លាស់ដែលធ្វើឲ្យខាតពេល។' (explaining / summary)
6. Ending / CTA: 'ចុះអ្នកវិញ កំពុងស្ថិតក្នុងស្ថានភាពមួយណា? ខមិនប្រាប់ខាងក្រោមមក!' (pointing down / CTA)
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
from ai_studio.util import ffmpeg_exe

# Anchored to the repo root so the output always lands in the folder the
# gallery serves (ai_studio/app.py mounts <repo>/outputs), even when this
# renderer is launched from another working directory.
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(REPO_ROOT, "outputs", "real_love_vs_situationship")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SCENES = [
    {
        "idx": 0,
        "title": "Hook",
        "text": "តើអ្នកកំពុងស្រឡាញ់គេ... ឬកំពុងនៅក្នុង Situationship?",
        "action": "surprised",
        "prop": "none",
        "visual_source": "character_action",
        "emotion": "surprised",
    },
    {
        "idx": 1,
        "title": "A: Real Love",
        "text": "ចំណុចទីមួយ បើជា Real Love គេតែងតែច្បាស់លាស់ យកចិត្តទុកដាក់ និងមិនដែលធ្វើឲ្យយើងឯកោឡើយ។",
        "action": "pointing_left",
        "prop": "sparkles",
        "visual_source": "character_action",
        "emotion": "happy",
    },
    {
        "idx": 2,
        "title": "B: Situationship",
        "text": "តែបើជា Situationship វិញ ផ្ញើសារដូចសង្សារ តែពេលសួររឿងអនាគត គេថាសុំពេលគិតសិន!",
        "action": "pointing_right",
        "prop": "phone",
        "visual_source": "character_action",
        "emotion": "confused",
    },
    {
        "idx": 3,
        "title": "Middle Meme Reaction",
        "text": "ឈឺចាប់បំផុត គឺពេលដឹងថាខ្លួនឯងគ្រាន់តែជាជម្រើសពេលគេអផ្សុក!",
        "action": "laughing",
        "prop": "none",
        "visual_source": "meme",
        "meme_type": "reaction_shock",
        "emotion": "excited",
    },
    {
        "idx": 4,
        "title": "Summary A vs B",
        "text": "សរុបមក Real Love គឺភាពច្បាស់លាស់ រីឯ Situationship គឺភាពមិនច្បាស់លាស់ដែលធ្វើឲ្យខាតពេល។",
        "action": "explaining",
        "prop": "book",
        "visual_source": "character_action",
        "emotion": "storytelling",
    },
    {
        "idx": 5,
        "title": "Ending & CTA",
        "text": "ចុះអ្នកវិញ កំពុងស្ថិតក្នុងស្ថានភាពមួយណា? ខមិនប្រាប់ខាងក្រោមមក!",
        "action": "pointing_down",
        "prop": "microphone",
        "visual_source": "character_action",
        "emotion": "happy",
    },
]


def render_project():
    os.environ.setdefault("STUDIO_DATA_DIR", os.path.join(REPO_ROOT, "data", "studio"))
    cfg = cfg_mod.load()
    tts_provider = tts.get_tts_provider(cfg)
    char_asset = os.path.join(REPO_ROOT, "ai_studio", "assets", "character_default.png")
    scene_clips = []
    ass_dialogues = []
    current_time = 0.0

    print("=== Step 1: Synthesizing Audio & Rendering Scene Clips ===")
    print("Using Edge-TTS provider: km-KH-PisethNeural")
    for s in SCENES:
        idx = s["idx"]
        text = s["text"]
        action = s["action"]
        emotion = s["emotion"]
        vs = s["visual_source"]

        # Validate script
        sc_check = qa.validate_khmer_script(text)
        assert sc_check["passed"], f"Script error in scene {idx}: {sc_check['issues']}"

        # 1. Synthesize audio
        audio_out = os.path.join(OUTPUT_DIR, f"scene_{idx}_audio.wav")
        res_tts = tts_provider.synthesize_to_file(text, audio_out, emotion=emotion)
        if not res_tts.get("ok"):
            res_tts = tts.synthesize(text, audio_out, cfg, emotion_style=emotion)
        assert res_tts["ok"]
        aud_check = qa.validate_voice_audio(audio_out)
        dur = max(2.5, aud_check["duration"])
        # Real measured length, so the QA gate checks pacing against the
        # audio it just made instead of its 3.0s placeholder default.
        s["audio_duration"] = dur
        s["estimated_duration_sec"] = dur

        # 2. Render visual clip
        video_out = os.path.join(OUTPUT_DIR, f"scene_{idx}_video.mp4")
        if vs == "meme":
            me.render_meme_clip(s["meme_type"], text[:28], video_out, dur, 720, 1280, 25)
        else:
            ca.render_character_action_clip(
                char_asset, action, video_out, dur, 720, 1280, 25,
                prop=s.get("prop"), audio_path=audio_out
            )

        # 3. Combine audio + video
        muxed_clip = os.path.join(OUTPUT_DIR, f"scene_{idx}_muxed.mp4")
        ff = ffmpeg_exe() or "ffmpeg"
        subprocess.check_call([
            ff, "-y", "-i", video_out, "-i", audio_out,
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
        ff, "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", assembled_raw
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("\n=== Step 3: Burning Subtitles via HarfBuzz ASS Shaper ===")
    ass_path = os.path.join(OUTPUT_DIR, "subtitles.ass")
    st, _ = cap.validate_style({"preset": "clean"})
    cap.build_ass(ass_dialogues, st, 720, 1280, ass_path)

    final_mp4 = os.path.join(OUTPUT_DIR, "Real_Love_vs_Situationship_Final.mp4")
    media.burn_ass(assembled_raw, ass_path, final_mp4)
    print(f"  ✓ Final video produced: {final_mp4} ({os.path.getsize(final_mp4)} bytes)")

    print("\n=== Step 4: Extracting Inspection Frames ===")
    frames = [
        ("frame_hook.png", 1.2),
        ("frame_real_love.png", 4.0),
        ("frame_situationship.png", 7.5),
        ("frame_meme.png", 11.0),
        ("frame_summary.png", 14.5),
        ("frame_ending.png", 18.0),
    ]
    for fname, t_sec in frames:
        fpath = os.path.join(OUTPUT_DIR, fname)
        subprocess.check_call([
            ff, "-y", "-ss", str(t_sec), "-i", final_mp4,
            "-vframes", "1", fpath
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"  ✓ Extracted {fname} at {t_sec}s")

    print("\n=== Step 5: Running QA Gate Verification ===")
    audio_sample = os.path.join(OUTPUT_DIR, "scene_0_audio.wav")
    if qa.validate_khmer_audio(audio_sample):
        print("  Khmer audio validation: PASSED")
    else:
        print("  Khmer audio validation: FAILED")
    full_qa = qa.run_full_project_qa(SCENES, final_mp4_path=final_mp4, content_type="compare")
    print("  QA Gate Approved:", full_qa["approved"])
    print("  Failures:", full_qa["failures"])
    print("  Warnings:", full_qa["warnings"])
    print("  MP4 Verified:", full_qa["mp4_verified"])
    assert full_qa["approved"], f"QA Gate failed: {full_qa['failures']}"
    assert full_qa["mp4_verified"]

    return final_mp4


if __name__ == "__main__":
    render_project()
