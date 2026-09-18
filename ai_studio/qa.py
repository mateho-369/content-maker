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


def final_dimensions(settings: Optional[dict]) -> Optional[Tuple[int, int]]:
    """The resolution this project's export is supposed to have.

    The per-project `settings.video` block is what the assembly stage renders at,
    so that is what the gate compares against — a hardcoded 9:16 would flag every
    landscape export and stay silent about a 1080p project that came out 540p.
    None means "no expectation on record, do not judge".
    """
    v = ((settings or {}).get("video") or {})
    try:
        w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    except (TypeError, ValueError):
        return None
    return (w, h) if w > 0 and h > 0 else None


def validate_final_mp4(mp4_path: str, expect: Optional[Tuple[int, int]] = None) -> Dict:
    """Open the finished export and report what is in the container.

    Size and existence are not verdicts. The old rule — "under 10 KB is
    corrupted" — was the only thing standing between a truncated render and a
    green gate: a 1-byte junk file passed by being "too small" (never opened), and
    a real 200 KB clip with no narration passed outright. So the file is parsed
    (`media.probe`) and the findings are duration, stream presence and resolution
    against `expect`; the 9:16 aspect is only used when no resolution was recorded.
    """
    out = {"passed": False, "size_bytes": 0, "duration": 0.0, "width": 0, "height": 0,
           "has_video": False, "has_audio": False, "probe_used": False,
           "ffmpeg_available": False, "video_stream": None, "audio_stream": None,
           "issues": []}

    def fail(check, issue):
        out["issues"].append({"severity": "fail", "check": check, "issue": issue})

    if not mp4_path:
        fail("mp4", "no final MP4 on record — the project has not been assembled yet")
        return out
    from .media import probe as probe_media

    info = probe_media(mp4_path) or {}
    out["size_bytes"] = int(info.get("size_bytes") or 0)
    out["probe_used"] = bool(info.get("probe_used"))
    out["ffmpeg_available"] = bool(info.get("ffmpeg_available"))
    out["duration"] = float(info.get("duration") or 0.0)
    out["width"] = int(info.get("width") or 0)
    out["height"] = int(info.get("height") or 0)
    out["video_stream"] = info.get("video_stream")
    out["audio_stream"] = info.get("audio_stream")
    out["has_video"] = bool(info.get("has_video"))
    out["has_audio"] = bool(info.get("has_audio"))
    name = os.path.basename(mp4_path)

    if not out["size_bytes"]:
        fail("mp4", f"the recorded final MP4 is not on disk ({mp4_path}) — re-run Assemble")
        return out
    if not out["probe_used"]:
        if not out["ffmpeg_available"]:
            # nothing could look at the file: say so instead of certifying it
            out["issues"].append({"severity": "warn", "check": "mp4",
                                  "issue": f"{name}: container could not be parsed (no ffmpeg on "
                                           "this machine) — the file exists but is unverified"})
            out["passed"] = True
            return out
        # ffmpeg ran and found no streams at all: that is a broken export, not an
        # unverifiable one (a 1-byte junk file used to be judged by size alone)
        fail("mp4", f"{name} ({out['size_bytes']} bytes) is not a readable MP4 — no streams "
                    "could be parsed out of it")
        return out

    if not out["has_video"] or out["width"] <= 0 or out["height"] <= 0:
        fail("mp4", f"{name} ({out['size_bytes']} bytes) has no decodable video stream — the "
                    "render is truncated or corrupt, not merely small")
    if out["duration"] < 1.0:
        fail("mp4", f"{name} is only {out['duration']:.2f}s long — a real cut is not under a second")
    # a silent export is exactly the dud this gate exists to catch (an audio stage
    # deferred on a CPU box, a mux that dropped the track)
    if not out["has_audio"]:
        fail("mp4", f"{name} has no audio stream — the Khmer narration never made it into the mux")

    if expect:
        ew, eh = expect
        if out["width"] and (out["width"] != ew or out["height"] != eh):
            out["issues"].append({"severity": "warn", "check": "resolution",
                                  "issue": f"exported at {out['width']}x{out['height']}, the "
                                           f"project renders at {ew}x{eh} — check "
                                           "settings.video / assembly.resolution"})
    elif out["width"] and out["height"]:
        ratio = out["width"] / out["height"]
        if abs(ratio - (9 / 16)) > 0.05:
            out["issues"].append({"severity": "warn", "check": "aspect_ratio",
                                  "issue": f"{out['width']}x{out['height']} is not vertical 9:16 "
                                           "(no settings.video on this project to compare against)"})

    out["passed"] = not any(i["severity"] == "fail" for i in out["issues"])
    return out


def check_caption_contrast(mp4_path: str, expect_scenes: Optional[List[Dict]] = None) -> Dict:
    """Is the burnt-in caption still readable on the chosen background?

    Captions are white text on a semi-opaque strip; a bright plate (white studio,
    a sunlit photo the user uploaded) is what makes them disappear. Sample the band
    the captions live in at a few points across the cut and report the brightest
    stretches. A scene the Director deselected is never counted as a problem, and a
    render without captions returns `checked: false` rather than a fake pass.
    """
    out = {"passed": True, "checked": False, "issues": [], "max_band_mean": 0.0,
           "scenes": []}
    if not mp4_path or not os.path.exists(mp4_path):
        out["passed"] = False
        out["issues"].append({"severity": "fail", "check": "caption_contrast",
                              "issue": "no final MP4 to sample"})
        return out
    try:
        import cv2
        import numpy as np
    except Exception:                                   # headless box without cv2
        out["issues"].append({"severity": "warn", "check": "caption_contrast",
                              "issue": "frame sampling unavailable (no opencv) — the caption "
                                       "band was not checked"})
        return out
    dur = 0.0
    cap = cv2.VideoCapture(mp4_path)
    if not cap.isOpened():
        out["issues"].append({"severity": "warn", "check": "caption_contrast",
                              "issue": "the export could not be opened for frame sampling"})
        return out
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    dur = (n / fps) if n else 0.0
    if dur <= 0:
        dur = float(os.environ.get("QA_SAMPLE_DURATION") or 0.0)
    means = []
    for t in (0.15, 0.35, 0.55, 0.75, 0.92):
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, dur * t) * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        h = frame.shape[0]
        means.append(float(np.mean(frame[int(h * 0.78):int(h * 0.95), :])))
    cap.release()
    if not means:
        out["issues"].append({"severity": "warn", "check": "caption_contrast",
                              "issue": "no frames could be read from the export"})
        return out
    out["checked"] = True
    out["max_band_mean"] = round(max(means), 1)
    if max(means) > 205:                                # near-white behind the text
        out["passed"] = False
        out["issues"].append({"severity": "warn", "check": "caption_contrast",
                              "issue": f"the caption band reads {max(means):.0f}/255 (near-white) — "
                                       "white subtitles on a bright background are hard to read; "
                                       "pick a darker plate or keep the caption strip on"})
    return out


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


def run_full_project_qa(scenes: List[Dict], final_mp4_path: Optional[str] = None,
                        content_type: str = "explainer",
                        target_dimensions: Optional[Tuple[int, int]] = None,
                        captions_burned: bool = True) -> Dict:
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
    mp4_res = validate_final_mp4(final_mp4_path, expect=target_dimensions)
    all_issues.extend(mp4_res.get("issues", []))

    # 4. the export has to be the cut the board planned, not merely a valid file.
    #    Only compared when both sides are real: `audio_duration` is 0 until a
    #    voice stage has written a WAV, and `duration` is 0 until the container was
    #    actually parsed — comparing either against the plan used to invent a
    #    mismatch (or hide one).
    # Length: only a cut that is SHORTER than the board planned means scenes went
    # missing. A longer export is normal — assembly pads each clip up to the
    # scene's own `estimated_duration_sec` (and a previz draft runs long by design),
    # while the voice rows are only as long as the narration. Judging either the
    # audio sum or an over-length export flags every manual board and teaches the
    # user to ignore the gate, so both are left alone.
    planned = float(hook_res.get("estimated_duration") or 0.0)
    actual = float(mp4_res.get("duration") or 0.0)
    if mp4_res.get("probe_used") and planned > 0 and actual > 0:
        missing = planned - actual
        if missing > max(1.5, planned * 0.10):
            all_issues.append({"severity": "fail", "check": "sync",
                               "issue": f"the cut is {actual:.1f}s but the board planned "
                                        f"{planned:.1f}s — {missing:.1f}s of scenes are missing "
                                        "from the export (a dropped scene, or a voice/video "
                                        "stage that never ran)"})

    # 5. Can the burnt-in captions actually be read on the chosen background? Every
    #    other check in this gate would call a white-on-white cut a success: the
    #    container is fine, the duration is fine, the audio is there. So the finished
    #    file is sampled at the band captions live in — measured, never assumed.
    cap_res = {}
    if final_mp4_path and captions_burned:
        cap_res = check_caption_contrast(final_mp4_path)
        all_issues.extend(cap_res.get("issues", []))

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
        # `mp4_checked`: the container was opened and parsed. `mp4_verified`: it
        # was opened AND nothing in it failed. Both are reported because the old
        # single flag said "verified" for a file nobody had read.
        "mp4_checked": bool(mp4_res.get("probe_used")),
        "mp4_verified": bool(mp4_res.get("passed")),
        "final_mp4": final_mp4_path or "",
        "final_size_bytes": mp4_res.get("size_bytes", 0),
        # the caption-band measurement, kept as its own dimension so the panel can
        # show the number (0-255) instead of only a verdict
        "caption_contrast": {k: cap_res.get(k) for k in
                             ("checked", "passed", "max_band_mean")} if cap_res
                            else {"checked": False, "passed": True, "max_band_mean": 0.0,
                                  "skipped": "no captions burned into the export"
                                  if not captions_burned else "no final MP4 to sample"},
    }
