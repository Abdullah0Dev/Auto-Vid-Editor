"""Final concat + audio mux with crossfade transitions."""
import subprocess
from pathlib import Path

from config import (
    FFMPEG, WORKSPACE_DIR, AUDIO_CODEC, AUDIO_BITRATE,
    VIDEO_CODEC, VIDEO_PRESET, VIDEO_CRF, FPS, RESOLUTION,
)
from pipeline import audio_mixer
from models.types import ImportantMoment
from utils.logger import log


XFADE_DURATION = 0.6  # seconds of overlap between scenes


def render(
    clip_paths: list[str],
    narration_video: str,
    output_path: str,
    important_moments: list[ImportantMoment],
    bg_music: str | None = None,
    nasheed: str | None = None,
):
    """Concatenate clips with crossfade transitions, then mux audio."""

    if len(clip_paths) == 0:
        raise RuntimeError("No clips to render")

    # 1. Get each clip's duration via ffprobe
    durations = [_probe_duration(p) for p in clip_paths]

    # 2. Build xfade filter chain
    if len(clip_paths) == 1:
        concat_video = clip_paths[0]
    else:
        concat_video = str(WORKSPACE_DIR / "concat_video.mp4")
        _xfade_concat(clip_paths, durations, concat_video)

    # 3. Build audio filter (unchanged)
    filter_str = audio_mixer.build_filter(
        important_moments,
        has_bg_music=bool(bg_music),
        has_nasheed=bool(nasheed),
    )

    # 4. Mux
    cmd = [FFMPEG, "-y", "-i", concat_video, "-i", narration_video]
    if bg_music:
        cmd += ["-i", bg_music]
    if nasheed:
        cmd += ["-i", nasheed]

    cmd += [
        "-filter_complex", filter_str,
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", AUDIO_CODEC, "-b:a", AUDIO_BITRATE,
        "-shortest", output_path,
    ]
    log.info(f"Rendering final video → {output_path}")
    subprocess.run(cmd, check=True, capture_output=True, text=True)
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