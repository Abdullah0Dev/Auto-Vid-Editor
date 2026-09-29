"""Final concat + audio mux with crossfade transitions."""
import subprocess
from pathlib import Path

from config import (
    FFMPEG, WORKSPACE_DIR, AUDIO_CODEC, AUDIO_BITRATE,
    VIDEO_CODEC, VIDEO_PRESET, VIDEO_CRF, FPS, RESOLUTION,
)
from pipeline import audio_mixer
from models.types import Scene, ImportantMoment
from utils.logger import log


XFADE_DURATION = 0.6  # seconds of overlap between scenes


def render(
    clip_paths: list[str],
    narration_video: str,
    output_path: str,
    important_moments: list[ImportantMoment] | None = None,
    scenes: list[Scene] | None = None,                # ← ADD THIS
    bg_music: str | None = None,
    nasheed: str | None = None,
):
    if not clip_paths:
        raise RuntimeError("No clips to render")

    important_moments = important_moments or []
    scenes = scenes or []
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Concatenate video clips ─────────────────────────────
    if len(clip_paths) == 1:
        concat_video = clip_paths[0]
    else:
        durations = [_probe_duration(p) for p in clip_paths]
        concat_video = str(WORKSPACE_DIR / "concat_video.mp4")
        _xfade_concat(clip_paths, durations, concat_video)

    # ── 2. Build audio filter ──────────────────────────────────
    filter_str = audio_mixer.build_filter(
        scenes=scenes,
        important_moments=important_moments,
        has_bg_music=bool(bg_music),
        has_nasheed=bool(nasheed),
    )

    # ── 3. Mux ─────────────────────────────────────────────────
    cmd = [FFMPEG, "-y", "-i", concat_video, "-i", narration_video]
    if bg_music:
        cmd += ["-i", bg_music]
    if nasheed:
        cmd += ["-i", nasheed]

    cmd += [
        "-filter_complex", filter_str,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", AUDIO_CODEC, "-b:a", AUDIO_BITRATE,
        "-shortest",
        output_path,
    ]

    log.info(f"Rendering final video → {output_path}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error(f"FFmpeg render failed (exit {result.returncode})")
        log.error(f"stderr: {result.stderr[-800:]}")
        raise RuntimeError("Render failed")
    log.ok(f"Done: {output_path}")


def _xfade_concat(clip_paths: list[str], durations: list[float], out: str):
    """
    Chain xfade transitions between all clips.
    Transition types: fade, wipeleft, wiperight, slideup, circleopen, etc.
    """
    # Rotation of transition styles for variety
    transitions = ["fade", "wipeleft", "fadeblack", "circleopen", "fade"]

    cmd = [FFMPEG, "-y"]
    for p in clip_paths:
        cmd += ["-i", p]

    # Build filter_complex
    filter_parts = []
    current = "[0:v]"
    cumulative = durations[0]

    for i in range(1, len(clip_paths)):
        offset = cumulative - XFADE_DURATION
        transition = transitions[i % len(transitions)]
        out_label = f"[v{i}]"
        filter_parts.append(
            f"{current}[{i}:v]xfade=transition={transition}:"
            f"duration={XFADE_DURATION}:offset={offset:.2f}{out_label}"
        )
        current = out_label
        cumulative += durations[i] - XFADE_DURATION

    filter_str = ";".join(filter_parts)

    cmd += [
        "-filter_complex", filter_str,
        "-map", current,
        "-c:v", VIDEO_CODEC, "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
        "-pix_fmt", "yuv420p",
        out,
    ]
    log.info(f"Applying crossfade transitions to {len(clip_paths)} clips...")
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _probe_duration(path: str) -> float:
    """Get duration of a video file in seconds."""
    r = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ], capture_output=True, text=True)
    return float(r.stdout.strip())