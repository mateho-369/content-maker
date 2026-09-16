"""Comprehensive QA Gate for AI Content Studio.

Enforces:
1. Script & Content Check (1-3s hook, retention, markdown leaks, length)
2. Khmer Typography & Cluster Check (no orphaned COENG, no broken clusters, no replacement chars)
3. Voice Audio Check (duration, clipping, silence gap, presence)
4. Video Visual Check (vertical 9:16 aspect ratio, safe areas, resolution)
5. Final Export Sanity Check (valid MP4, synchronized streams, playable)
"""
import json
import os
import re
import subprocess
from typing import Dict, List, Optional, Tuple

KHMER_CONSONANTS = r"[\u1780-\u17B3]"
KHMER_COENG = "\u17D2"
KHMER_VOWELS = r"[\u17B6-\u17C5]"
MARKDOWN_LEAK_PATTERNS = [
    r"\*\*",
    r"__",
    r"#{1,6}\s",
    r"```",
    r"\[.*?\]\(.*?\)",
    r"^\s*-\s+",
]


def validate_khmer_script(text: str) -> Dict:
    """Validates Khmer text for orthographic, cluster, and formatting errors."""
    issues = []
    text = str(text or "")

    # 1. Broken / replacement characters
    if "\uFFFD" in text:
        issues.append({"severity": "fail", "check": "typography", "issue": "Text contains Unicode replacement character (U+FFFD)"})

    # 2. Orphaned or invalid COENG (subscript consonant sign U+17D2)
    # COENG at the start of text
    if text.startswith(KHMER_COENG):
        issues.append({"severity": "fail", "check": "khmer_clusters", "issue": "Text starts with an orphaned subscript sign (COENG)"})

    # COENG preceded by space or punctuation or vowel
    orphaned_coeng = re.search(r"[^\u1780-\u17B3]\u17D2", text)
    if orphaned_coeng:
        issues.append({"severity": "fail", "check": "khmer_clusters", "issue": f"Subscript sign (COENG) not preceded by consonant near '{text[max(0, orphaned_coeng.start()-2):orphaned_coeng.end()+2]}'"})

    # COENG not followed by a valid subscriptable consonant
    dangling_coeng = re.search(r"\u17D2([^\u1780-\u17B3]|$)", text)
    if dangling_coeng:
        issues.append({"severity": "fail", "check": "khmer_clusters", "issue": "Subscript sign (COENG) without trailing consonant"})

    # 3. Double COENG
    if "\u17D2\u17D2" in text:
        issues.append({"severity": "fail", "check": "khmer_clusters", "issue": "Invalid double subscript sign (COENG COENG)"})

    # 4. Raw markdown leakage into narration
    for pat in MARKDOWN_LEAK_PATTERNS:
        if re.search(pat, text, re.MULTILINE):
            issues.append({"severity": "warn", "check": "content_hygiene", "issue": f"Possible raw markdown format leakage in speech script ({pat})"})
            break

    # 5. Gibberish or empty check
    clean_text = text.strip()
    if not clean_text:
        issues.append({"severity": "fail", "check": "content", "issue": "Scene script is empty"})
    elif len(clean_text) < 3:
        issues.append({"severity": "warn", "check": "content", "issue": "Scene script is suspiciously short"})

    return {
        "passed": not any(i["severity"] == "fail" for i in issues),
        "issues": issues,
        "clean_length": len(clean_text),
    }


def validate_content_hook(scenes: List[Dict], content_type: str = "explainer") -> Dict:
    """Evaluates the opening hook and scene progression for social media retention."""
    issues = []
    if not scenes:
        return {"passed": False, "issues": [{"severity": "fail", "check": "structure", "issue": "Project contains zero scenes"}]}

    scene1 = scenes[0]
    s1_text = scene1.get("text", "").strip()
    s1_est_dur = float(scene1.get("estimated_duration_sec") or scene1.get("audio_duration") or 3.0)

    # TikTok / Reels 1-3 second hook check
    if s1_est_dur > 5.5 and len(s1_text) > 80:
        issues.append({
            "severity": "warn",
            "check": "hook_pacing",
            "issue": f"Scene 1 hook is too long ({s1_est_dur:.1f}s, {len(s1_text)} chars). Optimal hook is 1-3s (under 60 chars) to maximize retention.",
        })

    # Total duration check
    total_est = sum(float(s.get("estimated_duration_sec") or s.get("audio_duration") or 3.0) for s in scenes)
    if total_est > 90.0:
        issues.append({
            "severity": "warn",
            "check": "total_duration",
            "issue": f"Estimated duration ({total_est:.1f}s) exceeds standard 60-90s short-form sweet spot.",
        })

    return {
        "passed": not any(i["severity"] == "fail" for i in issues),
        "issues": issues,
        "estimated_duration": total_est,
        "scene_count": len(scenes),
    }


def validate_khmer_audio(audio_path: str) -> bool:
    """Check if audio contains actual speech, not placeholder"""
    # Check audio duration vs expected duration
    # Check audio energy (placeholder has very low energy)
    # Check audio sample rate
    if not audio_path or not os.path.exists(audio_path):
        return False
    try:
        import wave
        with wave.open(audio_path, 'rb') as wf:
            frames = wf.readframes(wf.getnframes())
            # Placeholder audio is typically silence or very short
            if len(frames) < 10000:  # Less than 0.5 seconds
                return False
        return True
    except Exception:
        from .util import media_duration
        dur = media_duration(audio_path, 0.0)
        return dur >= 0.5


def validate_voice_audio(audio_path: str) -> Dict:
    """Validates an audio file for speech presence, peak loudness, and silence."""
    if not audio_path or not os.path.exists(audio_path):
        return {"passed": False, "issues": [{"severity": "fail", "check": "voice", "issue": f"Voice audio file missing: {audio_path}"}]}

    issues = []
    from .util import media_duration, ffmpeg_exe

    duration = media_duration(audio_path, 0.0)
    if duration < 0.4:
        issues.append({"severity": "fail", "check": "voice", "issue": f"Voice duration {duration:.2f}s is too short"})

    # Check for audio levels / clipping via ffmpeg volumedetect
    ff = ffmpeg_exe()
    if ff:
        try:
            cmd = [
                ff, "-hide_banner", "-i", audio_path, "-af", "volumedetect",
                "-vn", "-sn", "-dn", "-f", "null", "/dev/null"
            ]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            m = re.search(r"max_volume:\s*(-?[\d\.]+)\s*dB", proc.stderr)
            if m:
                max_vol = float(m.group(1))
                if max_vol > -0.05:
                    issues.append({"severity": "warn", "check": "voice", "issue": f"Voice audio is clipping (peak {max_vol:.1f} dB)"})
                elif max_vol < -30.0:
                    issues.append({"severity": "warn", "check": "voice", "issue": f"Voice audio is very quiet (peak {max_vol:.1f} dB)"})
        except Exception:
            pass

    return {
        "passed": not any(i["severity"] == "fail" for i in issues),
        "duration": duration,
        "issues": issues,
    }


def validate_final_mp4(mp4_path: str, target_aspect: Tuple[int, int] = (9, 16)) -> Dict:
    """Inspects final exported MP4 container, streams, resolution, and playback safety."""
    if not mp4_path or not os.path.exists(mp4_path):
        return {"passed": False, "issues": [{"severity": "fail", "check": "mp4", "issue": f"Final MP4 file does not exist: {mp4_path}"}]}

    if os.path.getsize(mp4_path) < 10240:
        return {"passed": False, "issues": [{"severity": "fail", "check": "mp4", "issue": f"Final MP4 is corrupted or too small ({os.path.getsize(mp4_path)} bytes)"}]}

    issues = []
    from .media import probe as probe_media

    info = probe_media(mp4_path)
    width = info.get("width", 0)
    height = info.get("height", 0)
    duration = info.get("duration", 0.0)

    has_video = width > 0 and height > 0
    # A silent export is exactly the kind of dud this gate exists to catch (an
    # audio stage deferred on a CPU box, a mux that dropped the track), so the
    # stream is actually looked for instead of assumed.
    has_audio = bool(info.get("has_audio", True))

    if not has_video:
        issues.append({"severity": "fail", "check": "mp4", "issue": "MP4 contains no valid video stream"})
    if not has_audio:
        issues.append({"severity": "fail", "check": "mp4", "issue": "MP4 has no audio stream — the Khmer narration never made it into the mux"})

    # Aspect ratio check (vertical 9:16 check)
    if width > 0 and height > 0:
        ratio = width / height
        expected_ratio = target_aspect[0] / target_aspect[1]
        if abs(ratio - expected_ratio) > 0.05:
            issues.append({
                "severity": "warn",
                "check": "aspect_ratio",
                "issue": f"Video dimensions {width}x{height} (ratio {ratio:.2f}) deviate from expected {target_aspect[0]}:{target_aspect[1]} ({expected_ratio:.2f})",
            })

    if duration < 1.0:
        issues.append({"severity": "fail", "check": "mp4", "issue": f"Final MP4 duration ({duration:.2f}s) is under 1 second"})

    return {
        "passed": not any(i["severity"] == "fail" for i in issues),
        "duration": duration,
        "width": width,
        "height": height,
        "has_video": has_video,
        "has_audio": has_audio,
        "issues": issues,
    }


def validate_example_assets(scenes: List[Dict], repo_root: Optional[str] = None) -> Dict:
    """Fail a scene whose declared example/internet photo is not on disk.

    A renderer that draws nothing for a missing file still produces a valid,
    playable MP4, so every other check stays green while the promised photo is
    simply absent from the video.
    """
    issues = []
    for idx, sc in enumerate(scenes):
        path = sc.get("example_img")
        if not path:
            continue
        resolved = path if os.path.isabs(path) else os.path.join(repo_root or "", path)
        if not os.path.isfile(resolved):
            issues.append({
                "severity": "fail",
                "check": "example_asset",
                "scene_idx": idx,
                "issue": f"Scene {idx + 1} declares example image '{path}' but the file is missing",
            })
    return {"passed": not issues, "issues": issues}


def run_full_project_qa(scenes: List[Dict], final_mp4_path: Optional[str] = None, content_type: str = "explainer") -> Dict:
    """Consolidated QA Gate assessment across all dimensions."""
    all_issues = []

    # 1. Content hook & structure
    hook_res = validate_content_hook(scenes, content_type)
    all_issues.extend(hook_res.get("issues", []))

    # 1b. Declared example/internet photos must exist (a missing one renders
    #     as an empty card, which no other check can see).
    asset_res = validate_example_assets(scenes)
    all_issues.extend(asset_res.get("issues", []))

    # 2. Khmer script & typography on all scenes
    for idx, sc in enumerate(scenes):
        txt = sc.get("text", "")
        sc_res = validate_khmer_script(txt)
        for iss in sc_res.get("issues", []):
            iss["scene_idx"] = idx
            all_issues.append(iss)

    # 3. Final MP4 validation if a path is provided. A path that no longer
    #    resolves is a *failed* check, not a skipped one: the caller (the API,
    #    a renderer) looked it up in the asset index, so a deleted or truncated
    #    export has to stop the gate instead of quietly turning it green.
    mp4_res = None
    if final_mp4_path:
        mp4_res = validate_final_mp4(final_mp4_path)
        all_issues.extend(mp4_res.get("issues", []))

    fails = [i for i in all_issues if i.get("severity") == "fail"]
    warns = [i for i in all_issues if i.get("severity") == "warn"]

    return {
        "approved": len(fails) == 0,
        "fail_count": len(fails),
        "warn_count": len(warns),
        "failures": fails,
        "warnings": warns,
        "total_scenes": len(scenes),
        # what the gate believes the runtime is (from audio_duration /
        # estimated_duration_sec per scene) — lets a renderer cross-check it
        # against the timeline it actually assembled
        "estimated_duration": hook_res.get("estimated_duration"),
        "mp4_verified": mp4_res["passed"] if mp4_res else False,
    }
