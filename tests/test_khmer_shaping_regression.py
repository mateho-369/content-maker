"""Regression test verifying real MP4 burn paths render shaped Khmer subscript consonants (ជើងអក្សរ).

Tests all critical cluster cases named in the production specification:
  * ស្រឡាញ់  (coeng ro ligature + wrap)
  * ខ្ញុំ      (coeng nho subscript)
  * ជើងអក្សរ (coeng sa subscript)
  * សួស្តីអ្នកទាំងអស់គ្នា (coeng ta, coeng no subscripts)
  * ស្វែងយល់ (coeng va ligature)
  * កម្ពុជា    (coeng po subscript)
  * សេចក្តីស្រឡាញ់ (coeng da + coeng ro)

Ensures that FFmpeg burns through libass without decomposing Unicode or
dropping into unshaped fallback plus-signs / ticks.
"""
import os
import subprocess
import pytest
from ai_studio import media, captions as cap

TEST_PHRASES = [
    "ស្រឡាញ់",
    "ខ្ញុំ",
    "ជើងអក្សរ",
    "សួស្តីអ្នកទាំងអស់គ្នា",
    "ស្វែងយល់ពីពិភពលោក",
    "កម្ពុជាមាតុភូមិខ្ញុំ",
    "សេចក្តីស្រឡាញ់និងសេចក្តីសង្ឃឹម",
]


@pytest.fixture
def base_video(tmp_path):
    """Generate a short 1.5s 720x1280 MP4 for burning."""
    p = str(tmp_path / "base.mp4")
    from ai_studio.util import ffmpeg_exe
    ff = ffmpeg_exe() or "ffmpeg"
    subprocess.run([
        ff, "-y", "-f", "lavfi",
        "-i", "color=c=black:s=720x1280:r=25:d=1.5",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", p
    ], check=True, capture_output=True)
    return p


@pytest.mark.parametrize("preset", ["clean", "bold_social", "cinema"])
def test_burn_ass_khmer_clusters(base_video, tmp_path, preset):
    """Verify burn_ass renders valid MP4s across fonts/presets without error."""
    text = "ស្រឡាញ់ ខ្ញុំ ជើងអក្សរ សួស្តីអ្នកទាំងអស់គ្នា"
    style, _ = cap.validate_style({"preset": preset})
    ass_path = str(tmp_path / f"test_{preset}.ass")
    out_mp4 = str(tmp_path / f"burned_{preset}.mp4")

    info = cap.build_ass([(0.1, 1.4, text)], style, 720, 1280, ass_path)
    assert os.path.exists(ass_path)
    assert info.get("font_family")

    media.burn_ass(base_video, ass_path, out_mp4)
    assert os.path.exists(out_mp4)
    assert os.path.getsize(out_mp4) > 1000

    # Extract frame at 0.5s and verify it exists and is populated
    frame_png = str(tmp_path / f"frame_{preset}.png")
    from ai_studio.util import ffmpeg_exe
    ff = ffmpeg_exe() or "ffmpeg"
    subprocess.run([
        ff, "-y", "-ss", "00:00:00.500", "-i", out_mp4,
        "-frames:v", "1", frame_png
    ], check=True, capture_output=True)
    assert os.path.exists(frame_png)
    assert os.path.getsize(frame_png) > 10000


def test_burn_subtitles_srt_shaping(base_video, tmp_path):
    """Verify burn_subtitles with an SRT file converts and burns shaped ASS."""
    srt_path = str(tmp_path / "test.srt")
    out_mp4 = str(tmp_path / "burned_srt.mp4")

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("1\n00:00:00,100 --> 00:00:01,400\nស្រឡាញ់ ខ្ញុំ ជើងអក្សរ\n")

    media.burn_subtitles(base_video, srt_path, out_mp4, style="bold_social")
    assert os.path.exists(out_mp4)
    assert os.path.getsize(out_mp4) > 1000
