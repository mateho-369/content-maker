"""Batch generation, rendering, frame extraction, and QA verification for 9 formats.

Required formats:
1. Explainer
2. What If
3. Compare
4. Choose
5. Word Nuance
6. Myth vs Fact
7. Quick Tip
8. Meme / Relatable
9. Emotional / Sad Story
"""
import os
import subprocess
import pytest
from ai_studio import character_actions as ca
from ai_studio import config as cfg_mod
from ai_studio import media
from ai_studio import meme_engine as me
from ai_studio import qa
from ai_studio.engines import tts

BATCH_FORMATS = [
    {
        "format": "explainer",
        "emotion": "calm",
        "action": "explaining",
        "prop": "book",
        "text": "តើអ្នកដឹងទេថាទឹកមានសារៈសំខាន់ខ្លាំងចំពោះខួរក្បាល? ការផឹកទឹកគ្រប់គ្រាន់ជួយបង្កើនការចងចាំ និងស្មារតីភ្លឺថ្លា។",
        "visual_source": "character_action",
    },
    {
        "format": "what_if",
        "emotion": "curious",
        "action": "thinking",
        "prop": "none",
        "text": "ចុះបើមនុស្សគ្រប់គ្នាឈប់ប្រើទូរស័ព្ទដៃមួយថ្ងៃ? យើងប្រហែលជានឹងចាប់ផ្តើមនិយាយរកគ្នាដោយក្តីស្រឡាញ់ឡើងវិញ។",
        "visual_source": "character_action",
    },
    {
        "format": "compare",
        "emotion": "serious",
        "action": "pointing",
        "prop": "none",
        "text": "សៀវភៅក្រដាស ឬសៀវភៅអេឡិចត្រូនិច តើមួយណាល្អជាង? សៀវភៅក្រដាសជួយអារម្មណ៍ស្ងប់ តែអេឡិចត្រូនិកងាយស្រួលយកតាមខ្លួន។",
        "visual_source": "character_action",
    },
    {
        "format": "choose",
        "emotion": "excited",
        "action": "celebrating",
        "prop": "sparkles",
        "text": "រវាងការភ្ញាក់ពីព្រលឹម និងការចូលគេងយប់ជ្រៅ តើអ្នករើសយកមួយណា? ភ្ញាក់ពីព្រលឹមផ្តល់ថាមពលស្រស់ស្រាយពេញមួយថ្ងៃ។",
        "visual_source": "character_action",
    },
    {
        "format": "word_nuance",
        "emotion": "storytelling",
        "action": "explaining",
        "prop": "book",
        "text": "ពាក្យ 'ស្មោះត្រង់' និងពាក្យ 'ស្មោះស្ម័គ្រ' មានអត្ថន័យខុសគ្នា។ ស្មោះត្រង់គឺមិនកុហក រីឯស្មោះស្ម័គ្រគឺការលះបង់ចេញពីបេះដូង។",
        "visual_source": "character_action",
    },
    {
        "format": "myth_vs_fact",
        "emotion": "surprised",
        "action": "confused",
        "prop": "none",
        "text": "ជំនឿថាការអានសៀវភៅក្នុងទីងងឹតធ្វើឲ្យខូចភ្នែកជារឿងមិនពិតទេ។ វាគ្រាន់តែធ្វើឲ្យភ្នែករបស់អ្នកឆាប់ហត់នឿយប៉ុណ្ណោះ។",
        "visual_source": "character_action",
    },
    {
        "format": "quick_tip",
        "emotion": "strong",
        "action": "pointing",
        "prop": "coffee",
        "text": "កុំផឹកកាហ្វេភ្លាមៗក្រោយភ្ញាក់ពីគេង! ចូររង់ចាំមួយម៉ោងដើម្បីឲ្យអរម៉ូនក្នុងខ្លួនដំណើរការតាមធម្មជាតិ។",
        "visual_source": "character_action",
    },
    {
        "format": "meme_relatable",
        "emotion": "excited",
        "action": "laughing",
        "prop": "none",
        "meme_type": "reaction_shock",
        "text": "ពេលដែលអ្នកប្រាប់ខ្លួនឯងថាសុំគេងតែ ៥ នាទីទៀត! ភ្ញាក់ឡើងម៉ោង ១១ ថ្ងៃត្រង់បាត់ទៅហើយ!",
        "visual_source": "meme",
    },
    {
        "format": "emotional_sad",
        "emotion": "sad",
        "action": "crying",
        "prop": "none",
        "text": "កន្លែងដដែល មនុស្សដែលធ្លាប់នៅក្បែរ ឥឡូវសល់ត្រឹមអនុស្សាវរីយ៍។ សេចក្តីស្រឡាញ់ខ្លះ គឺការរៀនលែងដៃដោយស្ងប់ស្ងាត់។",
        "visual_source": "character_action",
    },
]


@pytest.mark.parametrize("item", BATCH_FORMATS, ids=[b["format"] for b in BATCH_FORMATS])
def test_render_and_qa_format(tmp_path, item):
    fmt = item["format"]
    text = item["text"]
    cfg = cfg_mod.load()

    # 1. QA script & typography check
    script_check = qa.validate_khmer_script(text)
    assert script_check["passed"] is True, f"Khmer script validation failed for {fmt}: {script_check['issues']}"

    # 2. Synthesize audio with emotional styling
    audio_path = str(tmp_path / f"{fmt}_voice.wav")
    res_tts = tts.synthesize(text, audio_path, cfg, emotion_style=item["emotion"])
    assert res_tts["ok"] is True
    assert os.path.exists(audio_path)

    audio_qa = qa.validate_voice_audio(audio_path)
    assert audio_qa["passed"] is True
    dur = max(2.5, audio_qa["duration"])

    # 3. Render base video clip (720x1280 9:16 vertical)
    raw_video = str(tmp_path / f"{fmt}_raw.mp4")
    if item["visual_source"] == "meme":
        me.render_meme_clip(item.get("meme_type", "reaction_shock"), text[:25], raw_video, dur, 720, 1280, 25)
    else:
        ca.render_character_action_clip("", item["action"], raw_video, dur, 720, 1280, 25, item.get("prop", "none"))
    assert os.path.exists(raw_video)

    # 4. Generate subtitles & burn onto MP4
    srt_path = str(tmp_path / f"{fmt}.srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(f"1\n00:00:00,200 --> 00:00:{int(dur):02d},500\n{text}\n\n")

    final_mp4 = str(tmp_path / f"{fmt}_final.mp4")
    res_burn = media.burn_subtitles(raw_video, srt_path, final_mp4)
    assert os.path.exists(final_mp4)

    # 5. Extract inspection frames
    frame1 = str(tmp_path / f"{fmt}_frame1.png")
    frame2 = str(tmp_path / f"{fmt}_frame2.png")
    subprocess.check_call(["ffmpeg", "-y", "-ss", "0.8", "-i", final_mp4, "-vframes", "1", frame1],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call(["ffmpeg", "-y", "-ss", "1.8", "-i", final_mp4, "-vframes", "1", frame2],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert os.path.exists(frame1) and os.path.getsize(frame1) > 5000
    assert os.path.exists(frame2) and os.path.getsize(frame2) > 5000

    # 6. Full QA Gate Validation on final MP4
    scenes = [{"idx": 0, "text": text, "estimated_duration_sec": dur, "audio_duration": dur}]
    full_qa = qa.run_full_project_qa(scenes, final_mp4_path=final_mp4, content_type=fmt)
    assert full_qa["approved"] is True, f"QA Gate failed for format {fmt}: {full_qa['failures']}"
    assert full_qa["mp4_verified"] is True
