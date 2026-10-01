"""Final concat + audio mux with timeline-aware transitions."""

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


XFADE_DURATION = 0.6

BACKGROUND_COLOR = "0x0a0a1a"


# ============================================================
# Final render
# ============================================================

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

    scenes = sorted(
        scenes or [],
        key=lambda scene: scene.start,
    )

    WORKSPACE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output = Path(output_path)

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Inspect generated scene clips
    # --------------------------------------------------------

    durations = [
        _probe_duration(path)
        for path in clip_paths
    ]

    if scenes and len(scenes) == len(clip_paths):

        target_duration = max(
            float(scene.end)
            for scene in scenes
        )

        planned_durations = [
            max(
                float(scene.end - scene.start),
                0.0,
            )
            for scene in scenes
        ]

    else:

        target_duration = sum(durations)

        planned_durations = durations

        if scenes:
            log.warn(
                "Scene count does not match clip count. "
                "Using generated clip durations for the timeline."
            )

    target_duration = max(
        target_duration,
        0.01,
    )

    target_frames = max(
        round(target_duration * FPS),
        1,
    )

    target_duration = target_frames / FPS

    log.info(
        f"Target timeline: {target_duration:.3f}s"
    )

    log.info(
        f"Target frames: {target_frames} @ {FPS} FPS"
    )

    # --------------------------------------------------------
    # Scene duration diagnostics
    # --------------------------------------------------------

    for i, actual in enumerate(durations):

        if i < len(planned_durations):

            expected = planned_durations[i]

        else:

            expected = actual

        difference = actual - expected

        log.info(
            f"Scene {i + 1}: "
            f"planned={expected:.3f}s, "
            f"generated={actual:.3f}s, "
            f"difference={difference:+.3f}s"
        )

        tolerance = max(
            2.0 / FPS,
            0.05,
        )

        if abs(difference) > tolerance:

            log.warn(
                f"Scene {i + 1} has a duration mismatch. "
                "Check clip_builder output."
            )

    # --------------------------------------------------------
    # Build final video timeline
    # --------------------------------------------------------

    if len(clip_paths) == 1:

        concat_video = clip_paths[0]

        actual_video_duration = _probe_duration(
            concat_video
        )

        if actual_video_duration + (1.0 / FPS) < target_duration:

            raise RuntimeError(
                "Single scene is shorter than the approved timeline: "
                f"{actual_video_duration:.3f}s vs "
                f"{target_duration:.3f}s"
            )

    else:

        concat_video = str(
            WORKSPACE_DIR / "concat_video.mp4"
        )

        _xfade_concat(
            clip_paths,
            durations,
            concat_video,
            target_duration=target_duration,
            planned_durations=planned_durations,
        )

    # --------------------------------------------------------
    # Build audio filter chain
    # --------------------------------------------------------

    filter_str = audio_mixer.build_filter(
        scenes=scenes,
        important_moments=important_moments,
        has_bg_music=bool(bg_music),
        has_nasheed=bool(nasheed),
    )

    # Constrain the final mix to the same timeline as video.
    #
    # apad prevents a shorter audio stream from shortening
    # the final output.
    filter_str += (
        f";[aout]"
        f"apad,"
        f"atrim=duration={target_duration:.6f},"
        f"asetpts=PTS-STARTPTS"
        f"[afinal]"
    )

    # --------------------------------------------------------
    # FFmpeg input mapping
    # --------------------------------------------------------

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
        "[afinal]",

        # Do not use -shortest here.
        # The approved timeline determines output duration.
        "-t",
        f"{target_duration:.6f}",

        "-c:v",
        "copy",

        "-c:a",
        AUDIO_CODEC,

        "-b:a",
        AUDIO_BITRATE,

        "-movflags",
        "+faststart",

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

    # --------------------------------------------------------
    # Validate final output
    # --------------------------------------------------------

    actual_final = _probe_duration(
        str(output)
    )

    difference = actual_final - target_duration

    tolerance = max(
        2.0 / FPS,
        0.08,
    )

    if abs(difference) > tolerance:

        log.warn(
            f"Final duration differs from target: "
            f"{actual_final:.3f}s vs "
            f"{target_duration:.3f}s"
        )

    log.ok(
        f"Final render: {actual_final:.3f}s "
        f"(target {target_duration:.3f}s, "
        f"difference {difference:+.3f}s)"
    )


# ============================================================
# Timeline-aware crossfade concat
# ============================================================

def _xfade_concat(
    clip_paths: list[str],
    durations: list[float],
    out: str,
    target_duration: float | None = None,
    planned_durations: list[float] | None = None,
):
    """Join clips while preserving the planned total timeline.

    Each transition starts at the boundary between scenes.

    To prevent xfade from shortening the complete project, the
    accumulated outgoing stream is extended by the transition
    duration before each xfade.

    This avoids shifting all later scene boundaries earlier.
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

    for path, duration in zip(
        clip_paths,
        durations,
    ):

        if duration <= 0:

            raise RuntimeError(
                f"Invalid duration for {path}: {duration}"
            )

    if planned_durations is not None:

        if len(planned_durations) != len(clip_paths):

            raise RuntimeError(
                "Planned duration count does not match clip count"
            )

        timeline_durations = [
            max(float(value), 0.0)
            for value in planned_durations
        ]

    else:

        timeline_durations = durations

    if target_duration is None:

        target_duration = sum(
            timeline_durations
        )

    target_frames = max(
        round(target_duration * FPS),
        1,
    )

    target_duration = target_frames / FPS

    # --------------------------------------------------------
    # Choose a frame-aligned transition duration
    # --------------------------------------------------------

    shortest = min(
        durations
    )

    transition_duration = min(
        XFADE_DURATION,
        shortest / 2.0,
    )

    transition_frames = max(
        round(transition_duration * FPS),
        1,
    )

    transition_duration = (
        transition_frames / FPS
    )

    # Avoid a transition that consumes an entire short clip.
    if transition_duration >= shortest:

        raise RuntimeError(
            "Transition duration is too large for the shortest clip"
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

    # --------------------------------------------------------
    # Normalize all source streams
    # --------------------------------------------------------

    filter_parts = []

    for i in range(len(clip_paths)):

        filter_parts.append(
            f"[{i}:v:0]"
            f"scale={width}:{height}:"
            f"force_original_aspect_ratio=decrease:"
            f"force_divisible_by=2,"
            f"pad={width}:{height}:"
            f"(ow-iw)/2:(oh-ih)/2:"
            f"color={BACKGROUND_COLOR},"
            f"setsar=1,"
            f"fps={FPS},"
            f"format=yuv420p,"
            f"settb=1/{FPS},"
            f"setpts=PTS-STARTPTS"
            f"[n{i}]"
        )

    # --------------------------------------------------------
    # Chain transitions
    # --------------------------------------------------------

    transitions = [
        "fade",
        "wipeleft",
        "fadeblack",
        "circleopen",
        "fade",
    ]

    current = "[n0]"

    # The timeline boundary is based on planned scene durations,
    # not on the shortened xfade output duration.
    cumulative = timeline_durations[0]

    for i in range(1, len(clip_paths)):

        boundary = cumulative

        # Extend the outgoing timeline by one transition duration.
        #
        # This makes the incoming clip begin at the planned scene
        # boundary instead of shifting the timeline earlier.
        padded_label = f"[pad{i}]"

        filter_parts.append(
            f"{current}"
            f"tpad=stop_mode=clone:"
            f"stop_duration={transition_duration:.6f}"
            f"{padded_label}"
        )

        transition = transitions[
            (i - 1) % len(transitions)
        ]

        out_label = f"[v{i}]"

        filter_parts.append(
            f"{padded_label}[n{i}]"
            f"xfade="
            f"transition={transition}:"
            f"duration={transition_duration:.6f}:"
            f"offset={boundary:.6f}"
            f"{out_label}"
        )

        current = out_label

        cumulative += timeline_durations[i]

    # --------------------------------------------------------
    # Exact final timeline constraint
    # --------------------------------------------------------

    # This is a final frame-count safeguard. It should only trim
    # a tiny frame-rounding difference after the scene durations
    # and transition offsets have been aligned.
    filter_parts.append(
        f"{current}"
        f"tpad=stop_mode=clone:"
        f"stop_duration={transition_duration:.6f},"
        f"fps={FPS},"
        f"trim=end_frame={target_frames},"
        f"setpts=PTS-STARTPTS,"
        f"format=yuv420p"
        f"[vfinal]"
    )

    filter_str = ";".join(
        filter_parts
    )

    cmd += [
        "-filter_complex",
        filter_str,

        "-map",
        "[vfinal]",

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

        "-frames:v",
        str(target_frames),

        "-t",
        f"{target_duration:.6f}",

        "-movflags",
        "+faststart",

        out,
    ]

    log.info(
        f"Applying timeline-aware transitions "
        f"to {len(clip_paths)} clips"
    )

    log.info(
        f"Transition duration: {transition_duration:.3f}s"
    )

    log.info(
        f"Target duration: {target_duration:.3f}s"
    )

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:

        log.error(
            "FFmpeg xfade concat failed"
        )

        log.error(
            result.stderr[-5000:]
        )

        raise RuntimeError(
            "Crossfade concat failed"
        )

    actual = _probe_duration(out)

    tolerance = max(
        2.0 / FPS,
        0.08,
    )

    if abs(actual - target_duration) > tolerance:

        raise RuntimeError(
            "Concatenated video duration mismatch: "
            f"expected {target_duration:.3f}s, "
            f"generated {actual:.3f}s"
        )

    log.ok(
        f"Video timeline assembled: "
        f"{actual:.3f}s"
    )


# ============================================================
# Configuration helpers
# ============================================================

def _parse_resolution() -> tuple[int, int]:
    """Convert config resolution such as 1920x1080 to integers."""

    try:

        width_str, height_str = RESOLUTION.lower().split(
            "x",
            1,
        )

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


def _probe_duration(path: str) -> float:
    """Get duration of a media file in seconds."""

    result = subprocess.run(
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

    if result.returncode != 0:

        raise RuntimeError(
            f"Could not probe duration: {path}\n"
            f"{result.stderr}"
        )

    value = result.stdout.strip()

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