"""Build per-scene clips with Ken Burns, effects, animations, and B-roll volume.

Every generated clip is normalized to the configured resolution and FPS.

The visual stream is constrained to the intended scene frame count so
short source audio cannot accidentally truncate a scene.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from config import (
    FFMPEG,
    FPS,
    RESOLUTION,
    VIDEO_CODEC,
    VIDEO_PRESET,
    VIDEO_CRF,
    CLIPS_DIR,
)

from models.types import Scene
from utils.logger import log


VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".webm",
    ".m4v",
}

BACKGROUND_COLOR = "0x0a0a1a"


# ============================================================
# Configuration helpers
# ============================================================

def _parse_resolution() -> tuple[int, int]:
    """Parse configured resolution such as 1920x1080."""

    try:
        width_str, height_str = RESOLUTION.lower().split("x", 1)

        width = int(width_str)
        height = int(height_str)

    except (ValueError, AttributeError):
        raise RuntimeError(
            f"Invalid RESOLUTION: {RESOLUTION!r}. "
            "Expected format like '1920x1080'."
        )

    if width <= 0 or height <= 0:
        raise RuntimeError(
            f"Invalid dimensions: {width}x{height}"
        )

    return width, height


def _target_frames(duration: float) -> int:
    """Calculate the exact target number of video frames."""

    return max(
        round(duration * FPS),
        1,
    )


def _target_duration(duration: float) -> float:
    """Return duration rounded to the configured frame grid."""

    return _target_frames(duration) / FPS


def _has_audio(path: str) -> bool:
    """Check whether a source contains an audio stream."""

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            path,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return False

    return bool(result.stdout.strip())


def _probe_duration(path: str) -> float:
    """Read the generated file duration."""

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
            f"Could not inspect generated clip: {path}\n"
            f"{result.stderr}"
        )

    try:
        return float(result.stdout.strip())

    except ValueError:
        raise RuntimeError(
            f"Invalid duration returned for {path}: "
            f"{result.stdout!r}"
        )


def _run_ffmpeg(cmd: list[str], description: str):
    """Execute FFmpeg and report useful errors."""

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        log.error(
            f"{description} failed:"
        )

        log.error(
            result.stderr[-5000:]
        )

        raise RuntimeError(
            f"{description} failed"
        )


def _validate_clip(
    path: str,
    expected_duration: float,
    scene_id: int,
):
    """Validate generated clip duration against the target frame grid."""

    actual = _probe_duration(path)

    expected = _target_duration(
        expected_duration
    )

    tolerance = 1.5 / FPS

    difference = abs(actual - expected)

    if difference > tolerance:
        raise RuntimeError(
            f"Scene {scene_id} duration mismatch: "
            f"expected {expected:.3f}s, "
            f"generated {actual:.3f}s."
        )

    log.info(
        f"  Scene {scene_id}: "
        f"{actual:.3f}s / {expected:.3f}s "
        f"validated"
    )


# ============================================================
# Build all scenes
# ============================================================

def build_all(
    video_path: str,
    scenes: list[Scene],
) -> list[str]:

    CLIPS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    paths = []

    for i, scene in enumerate(scenes):

        out = str(
            CLIPS_DIR / f"clip_{scene.id:03d}.mp4"
        )

        _build_one(
            video_path,
            scene,
            out,
            is_first=(i == 0),
            is_last=(i == len(scenes) - 1),
            fit_mode=scene.fit_mode,
        )

        expected_duration = max(
            scene.end - scene.start,
            0.01,
        )

        _validate_clip(
            out,
            expected_duration,
            scene.id,
        )

        paths.append(out)

    log.ok(
        f"{len(paths)} clips built and validated"
    )

    return paths


# ============================================================
# Scene dispatcher
# ============================================================

def _build_one(
    video_path: str,
    scene: Scene,
    out: str,
    is_first: bool = False,
    is_last: bool = False,
    fit_mode: str = "contain",
):

    duration = max(
        float(scene.end - scene.start),
        0.01,
    )

    volume = max(
        0.0,
        min(float(scene.volume), 1.0),
    )

    if scene.visual_type == "recording":

        _trim_recording(
            video_path,
            scene.start,
            duration,
            out,
            is_first,
            is_last,
            volume=volume,
        )

    elif (
        scene.chosen_asset
        and Path(scene.chosen_asset).exists()
    ):

        asset = Path(scene.chosen_asset)
        ext = asset.suffix.lower()

        if (
            scene.visual_type == "graphic"
            or ext in VIDEO_EXTENSIONS
        ):

            log.info(
                f"  Scene {scene.id}: video "
                f"({asset.name}) "
                f"[fit={fit_mode}] "
                f"[volume={round(volume * 100)}%]"
            )

            _process_graphic_video(
                str(asset),
                duration,
                out,
                is_first,
                is_last,
                fit_mode=fit_mode,
                volume=volume,
            )

        else:

            log.info(
                f"  Scene {scene.id}: ken_burns "
                f"({asset.name}) "
                f"[fit={fit_mode}]"
            )

            _ken_burns(
                str(asset),
                duration,
                scene.ken_burns,
                out,
                is_first,
                is_last,
                fit_mode=fit_mode,
            )

    else:

        log.warn(
            f"  Scene {scene.id}: no asset → placeholder"
        )

        _placeholder(
            duration,
            out,
            is_first,
            is_last,
        )


# ============================================================
# Visual filter helper
# ============================================================

def _build_visual_filters(
    scene: Scene,
    duration: float,
    is_first: bool,
    is_last: bool,
) -> str:
    """Compose reusable visual filters."""

    width, height = _parse_resolution()

    filters = [
        (
            f"scale={width}:{height}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:"
            f"(ow-iw)/2:(oh-ih)/2:"
            f"color={BACKGROUND_COLOR}"
        )
    ]

    if is_first:
        filters.append(
            "fade=t=in:st=0:d=1.2"
        )

    if is_last:
        filters.append(
            f"fade=t=out:"
            f"st={max(duration - 1.2, 0):.3f}:"
            "d=1.2"
        )

    filters.extend([
        "eq=saturation=0.85:contrast=1.05:brightness=-0.02",
        "colorbalance=rs=0.05:gs=0.0:bs=-0.05",
        "vignette=PI/5",
        "format=yuv420p",
    ])

    return ",".join(filters)


# ============================================================
# Ken Burns images
# ============================================================

def _ken_burns(
    image: str,
    duration: float,
    direction: str,
    out: str,
    is_first: bool = False,
    is_last: bool = False,
    fit_mode: str = "contain",
):

    width, height = _parse_resolution()

    frames = _target_frames(duration)

    actual_duration = frames / FPS

    kb = {
        "zoom_in": (
            "z='min(zoom+0.0015,1.3)'"
        ),
        "zoom_out": (
            "z='if(lte(zoom,1.0),1.3,"
            "max(1.001,zoom-0.0015))'"
        ),
        "pan_left": (
            "z='1.2':"
            "x='if(lte(on,1),iw/4,iw/4-on*2)':"
            "y='ih/4'"
        ),
        "pan_right": (
            "z='1.2':"
            "x='if(lte(on,1),0,on*2)':"
            "y='ih/4'"
        ),
    }.get(
        direction,
        "z='min(zoom+0.0015,1.3)'",
    )

    if fit_mode == "cover":

        scale_pad = (
            f"scale={width}:{height}:"
            "force_original_aspect_ratio=increase,"
            f"crop={width}:{height}"
        )

    else:

        scale_pad = (
            f"scale={width}:{height}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:"
            f"(ow-iw)/2:(oh-ih)/2:"
            f"color={BACKGROUND_COLOR}"
        )

    vf_parts = [
        scale_pad,

        (
            f"zoompan={kb}:"
            f"d=1:"
            f"s={width}x{height}:"
            f"fps={FPS}"
        ),

        "eq=saturation=0.92:contrast=1.05:brightness=-0.02",
        "vignette=PI/5",
    ]

    if is_first:
        vf_parts.append(
            "fade=t=in:st=0:d=1.0"
        )

    if is_last:
        vf_parts.append(
            f"fade=t=out:"
            f"st={max(actual_duration - 1.0, 0):.3f}:"
            "d=1.0"
        )

    vf_parts.extend([
        f"fps={FPS}",
        "format=yuv420p",
    ])

    cmd = [
        FFMPEG,
        "-y",
        "-loop", "1",
        "-i", image,
        "-vf", ",".join(vf_parts),
        "-frames:v", str(frames),
        "-an",
        "-c:v", VIDEO_CODEC,
        "-preset", VIDEO_PRESET,
        "-crf", str(VIDEO_CRF),
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        out,
    ]

    _run_ffmpeg(
        cmd,
        f"Ken Burns scene generation: {image}",
    )


# ============================================================
# Existing video / Remotion graphics / B-roll
# ============================================================

def _process_graphic_video(
    video: str,
    duration: float,
    out: str,
    is_first: bool = False,
    is_last: bool = False,
    fit_mode: str = "contain",
    volume: float = 1.0,
):
    """Normalize an existing video to the exact scene frame count.

    Source audio is retained when present, volume-controlled, and
    padded or trimmed independently of the video stream.
    """

    width, height = _parse_resolution()

    frames = _target_frames(duration)

    actual_duration = frames / FPS

    volume = max(
        0.0,
        min(float(volume), 1.0),
    )

    if fit_mode == "cover":

        scale_pad = (
            f"scale={width}:{height}:"
            "force_original_aspect_ratio=increase,"
            f"crop={width}:{height}"
        )

    else:

        scale_pad = (
            f"scale={width}:{height}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:"
            f"(ow-iw)/2:(oh-ih)/2:"
            f"color={BACKGROUND_COLOR}"
        )

    vf_parts = [
        scale_pad,

        "eq=saturation=0.92:contrast=1.05:brightness=-0.02",

        "vignette=PI/5",
    ]

    if is_first:
        vf_parts.append(
            "fade=t=in:st=0:d=1.0"
        )

    if is_last:
        vf_parts.append(
            f"fade=t=out:"
            f"st={max(actual_duration - 1.0, 0):.3f}:"
            "d=1.0"
        )

    # Extend a short source by cloning its last frame.
    # Then enforce the exact requested output frame count.
    vf_parts.extend([
        (
            f"tpad=stop_mode=clone:"
            f"stop_duration={actual_duration:.6f}"
        ),
        f"fps={FPS}",
        f"trim=end_frame={frames}",
        "setpts=PTS-STARTPTS",
        "format=yuv420p",
    ])

    has_audio = _has_audio(video)

    cmd = [
        FFMPEG,
        "-y",
        "-i", video,
        "-map", "0:v:0",
        "-vf", ",".join(vf_parts),
    ]

    if has_audio:

        cmd += [
            "-map", "0:a:0?",
            "-af",
            (
                f"volume={volume:.4f},"
                "apad,"
                f"atrim=duration={actual_duration:.6f},"
                "asetpts=PTS-STARTPTS"
            ),
            "-c:a", "aac",
            "-b:a", "192k",
        ]

    else:

        cmd += [
            "-an",
        ]

    cmd += [
        "-frames:v", str(frames),
        "-t", f"{actual_duration:.6f}",
        "-c:v", VIDEO_CODEC,
        "-preset", VIDEO_PRESET,
        "-crf", str(VIDEO_CRF),
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        out,
    ]

    _run_ffmpeg(
        cmd,
        f"Video scene processing: {video}",
    )


# ============================================================
# Original recording segments
# ============================================================

def _trim_recording(
    video: str,
    start: float,
    duration: float,
    out: str,
    is_first: bool = False,
    is_last: bool = False,
    volume: float = 1.0,
):
    """Trim a source recording while preserving its intended duration."""

    width, height = _parse_resolution()

    frames = _target_frames(duration)

    actual_duration = frames / FPS

    volume = max(
        0.0,
        min(float(volume), 1.0),
    )

    vf_parts = [
        (
            f"scale={width}:{height}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:"
            f"(ow-iw)/2:(oh-ih)/2:"
            f"color={BACKGROUND_COLOR}"
        ),

        "eq=saturation=0.95:contrast=1.02",
    ]

    if is_first:
        vf_parts.append(
            "fade=t=in:st=0:d=1.0"
        )

    if is_last:
        vf_parts.append(
            f"fade=t=out:"
            f"st={max(actual_duration - 1.0, 0):.3f}:"
            "d=1.0"
        )

    vf_parts.extend([
        (
            f"tpad=stop_mode=clone:"
            f"stop_duration={actual_duration:.6f}"
        ),
        f"fps={FPS}",
        f"trim=end_frame={frames}",
        "setpts=PTS-STARTPTS",
        "format=yuv420p",
    ])

    has_audio = _has_audio(video)

    cmd = [
        FFMPEG,
        "-y",
        "-ss", f"{start:.6f}",
        "-i", video,
        "-map", "0:v:0",
        "-vf", ",".join(vf_parts),
    ]

    if has_audio:

        cmd += [
            "-map", "0:a:0?",
            "-af",
            (
                f"volume={volume:.4f},"
                "apad,"
                f"atrim=duration={actual_duration:.6f},"
                "asetpts=PTS-STARTPTS"
            ),
            "-c:a", "aac",
            "-b:a", "192k",
        ]

    else:

        cmd += ["-an"]

    cmd += [
        "-frames:v", str(frames),
        "-t", f"{actual_duration:.6f}",
        "-c:v", VIDEO_CODEC,
        "-preset", VIDEO_PRESET,
        "-crf", str(VIDEO_CRF),
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        out,
    ]

    _run_ffmpeg(
        cmd,
        f"Recording scene trim: {video}",
    )


# ============================================================
# Placeholder
# ============================================================

def _placeholder(
    duration: float,
    out: str,
    is_first: bool = False,
    is_last: bool = False,
):

    width, height = _parse_resolution()

    frames = _target_frames(duration)

    actual_duration = frames / FPS

    vf_parts = []

    if is_first:
        vf_parts.append(
            "fade=t=in:st=0:d=1.0"
        )

    if is_last:
        vf_parts.append(
            f"fade=t=out:"
            f"st={max(actual_duration - 1.0, 0):.3f}:"
            "d=1.0"
        )

    vf_parts.extend([
        "format=yuv420p",
    ])

    cmd = [
        FFMPEG,
        "-y",
        "-f", "lavfi",
        "-i",
        (
            f"color=c={BACKGROUND_COLOR}:"
            f"s={width}x{height}:"
            f"r={FPS}:"
            f"d={actual_duration:.6f}"
        ),
        "-vf", ",".join(vf_parts),
        "-frames:v", str(frames),
        "-an",
        "-c:v", VIDEO_CODEC,
        "-preset", "ultrafast",
        "-crf", "28",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        out,
    ]

    _run_ffmpeg(
        cmd,
        "Placeholder scene generation",
    )
