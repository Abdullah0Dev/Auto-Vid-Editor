"""Final concat + audio mux with crossfade transitions."""

from __future__ import annotations

import subprocess
from pathlib import Path

from config import (
    FFMPEG,
    WORKSPACE_DIR,
    AUDIO_CODEC,
    AUDIO_BITRATE,
    VIDEO_CODEC,
    VIDEO_PRESET,
    VIDEO_CRF,
    FPS,
    RESOLUTION,
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
    scenes: list[Scene] | None = None,
    bg_music: str | None = None,
    nasheed: str | None = None,
):
    if not clip_paths:
        raise RuntimeError("No clips to render")

    important_moments = important_moments or []
    scenes = scenes or []

    WORKSPACE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output = Path(output_path)
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ============================================================
    # 1. Concatenate video clips
    # ============================================================

    if len(clip_paths) == 1:
        concat_video = clip_paths[0]

    else:
        durations = [
            _probe_duration(path)
            for path in clip_paths
        ]

        concat_video = str(
            WORKSPACE_DIR / "concat_video.mp4"
        )

        _xfade_concat(
            clip_paths,
            durations,
            concat_video,
        )

    # ============================================================
    # 2. Build audio filter
    # ============================================================

    filter_str = audio_mixer.build_filter(
        scenes=scenes,
        important_moments=important_moments,
        has_bg_music=bool(bg_music),
        has_nasheed=bool(nasheed),
    )

    # ============================================================
    # 3. Mux final video + narration/music
    # ============================================================

    cmd = [
        FFMPEG,
        "-y",
        "-i",
        concat_video,
        "-i",
        narration_video,
    ]

    if bg_music:
        cmd += [
            "-i",
            bg_music,
        ]

    if nasheed:
        cmd += [
            "-i",
            nasheed,
        ]

    cmd += [
        "-filter_complex",
        filter_str,

        "-map",
        "0:v:0",

        "-map",
        "[aout]",

        "-c:v",
        "copy",

        "-c:a",
        AUDIO_CODEC,

        "-b:a",
        AUDIO_BITRATE,

        "-movflags",
        "+faststart",

        "-shortest",

        str(output),
    ]

    log.info(
        f"Rendering final video → {output}"
    )

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        log.error(
            f"FFmpeg render failed "
            f"(exit {result.returncode})"
        )

        log.error(
            f"stderr:\n{result.stderr[-5000:]}"
        )

        raise RuntimeError(
            "Render failed"
        )

    log.ok(
        f"Done: {output}"
    )


def _parse_resolution() -> tuple[int, int]:
    """Convert config resolution such as 1920x1080 to integers."""

    try:
        width_str, height_str = RESOLUTION.lower().split("x", 1)

        width = int(width_str)
        height = int(height_str)

    except (ValueError, AttributeError):
        raise RuntimeError(
            f"Invalid RESOLUTION configuration: {RESOLUTION!r}. "
            "Expected format like '1920x1080'."
        )

    if width <= 0 or height <= 0:
        raise RuntimeError(
            f"Invalid video dimensions: {width}x{height}"
        )

    return width, height


def _xfade_concat(
    clip_paths: list[str],
    durations: list[float],
    out: str,
):
    """
    Safely concatenate clips using xfade.

    All inputs are normalized to:

        configured resolution
        configured FPS
        yuv420p
        square pixels
        time base 1/FPS

    Normalization handles differences between regular
    FFmpeg clips and Remotion-generated graphics.
    """

    if len(clip_paths) < 2:
        raise RuntimeError(
            "_xfade_concat requires at least two clips"
        )

    if len(clip_paths) != len(durations):
        raise RuntimeError(
            "Clip paths and duration counts do not match"
        )

    width, height = _parse_resolution()

    # ------------------------------------------------------------
    # Validate durations
    # ------------------------------------------------------------

    for path, duration in zip(clip_paths, durations):
        if duration <= 0:
            raise RuntimeError(
                f"Invalid duration for {path}: {duration}"
            )

    # ------------------------------------------------------------
    # Use a safe transition duration.
    #
    # A transition must not consume too much of the
    # shortest source clip.
    # ------------------------------------------------------------

    shortest = min(durations)

    safe_duration = min(
        XFADE_DURATION,
        shortest / 2.0,
    )

    safe_duration = round(
        safe_duration,
        3,
    )

    if safe_duration <= 0:
        raise RuntimeError(
            "Invalid clip duration for xfade"
        )

    cmd = [
        FFMPEG,
        "-y",
    ]

    for path in clip_paths:
        cmd += [
            "-i",
            path,
        ]

    # ------------------------------------------------------------
    # Normalize every video stream.
    # ------------------------------------------------------------

    filter_parts = []

    for i in range(len(clip_paths)):
        filter_parts.append(
            f"[{i}:v:0]"
            f"scale={width}:{height}:"
            f"force_original_aspect_ratio=decrease:"
            f"force_divisible_by=2,"
            f"pad={width}:{height}:"
            f"(ow-iw)/2:(oh-ih)/2:"
            f"color=0x0a0a1a,"
            f"setsar=1,"
            f"fps={FPS},"
            f"format=yuv420p,"
            f"settb=1/{FPS},"
            f"setpts=PTS-STARTPTS"
            f"[n{i}]"
        )

    # ------------------------------------------------------------
    # Chain xfade filters.
    # ------------------------------------------------------------

    transitions = [
        "fade",
        "wipeleft",
        "fadeblack",
        "circleopen",
        "fade",
    ]

    current = "[n0]"

    # Use measured clip durations.
    #
    # Each transition overlaps the previous accumulated
    # output by safe_duration.
    cumulative = durations[0]

    for i in range(1, len(clip_paths)):

        offset = max(
            cumulative - safe_duration,
            0.0,
        )

        transition = transitions[
            (i - 1) % len(transitions)
        ]

        out_label = f"[v{i}]"

        filter_parts.append(
            f"{current}[n{i}]"
            f"xfade="
            f"transition={transition}:"
            f"duration={safe_duration}:"
            f"offset={offset:.6f}"
            f"{out_label}"
        )

        current = out_label

        cumulative += (
            durations[i] - safe_duration
        )

    filter_str = ";".join(
        filter_parts
    )

    cmd += [
        "-filter_complex",
        filter_str,

        "-map",
        current,

        "-an",

        "-c:v",
        VIDEO_CODEC,

        "-preset",
        VIDEO_PRESET,

        "-crf",
        str(VIDEO_CRF),

        "-pix_fmt",
        "yuv420p",

        "-r",
        str(FPS),

        "-movflags",
        "+faststart",

        out,
    ]

    log.info(
        f"Applying crossfade transitions "
        f"to {len(clip_paths)} clips..."
    )

    log.info(
        f"Output: {width}x{height} @ {FPS} FPS"
    )

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:

        log.error(
            "FFmpeg xfade concat failed:"
        )

        log.error(
            result.stderr[-5000:]
        )

        raise RuntimeError(
            "Crossfade concat failed"
        )


def _probe_duration(path: str) -> float:
    """Get duration of a video file in seconds."""

    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        capture_output=True,
        text=True,
    )

    if r.returncode != 0:
        raise RuntimeError(
            f"Could not probe duration: {path}\n"
            f"{r.stderr}"
        )

    value = r.stdout.strip()

    if not value:
        raise RuntimeError(
            f"No duration returned for: {path}"
        )

    try:
        duration = float(value)

    except ValueError:
        raise RuntimeError(
            f"Invalid duration returned for {path}: {value!r}"
        )

    if duration <= 0:
        raise RuntimeError(
            f"Non-positive duration for {path}: {duration}"
        )

    return duration
