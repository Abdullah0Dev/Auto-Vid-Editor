"""Build per-scene clips with Ken Burns, effects, animations, and B-roll volume."""

import subprocess
from pathlib import Path

from config import (
    FFMPEG, FPS, RESOLUTION, VIDEO_CODEC, VIDEO_PRESET,
    VIDEO_CRF, CLIPS_DIR,
)
from models.types import Scene
from utils.logger import log


VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".m4v"}


def build_all(video_path: str, scenes: list[Scene]) -> list[str]:
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)

    paths = []

    for i, scene in enumerate(scenes):
        out = str(CLIPS_DIR / f"clip_{scene.id:03d}.mp4")

        _build_one(
            video_path,
            scene,
            out,
            is_first=(i == 0),
            is_last=(i == len(scenes) - 1),
            fit_mode=scene.fit_mode,
        )

        paths.append(out)

    log.ok(f"{len(paths)} clips built")
    return paths


def _build_one(
    video_path: str,
    scene: Scene,
    out: str,
    is_first: bool = False,
    is_last: bool = False,
    fit_mode: str = "contain",
):
    duration = max(scene.end - scene.start, 0.01)

    # Clamp volume defensively even if an invalid value reaches us.
    volume = max(0.0, min(float(scene.volume), 1.0))

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

    elif scene.chosen_asset and Path(scene.chosen_asset).exists():
        asset = Path(scene.chosen_asset)
        ext = asset.suffix.lower()

        # Rendered Remotion graphics and downloaded B-roll videos
        # are already videos. Do NOT send them through Ken Burns.
        if scene.visual_type == "graphic" or ext in VIDEO_EXTENSIONS:
            log.info(
                f"  Scene {scene.id}: video "
                f"({asset.name}) [fit={fit_mode}] "
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
                f"({asset.name}) [fit={fit_mode}]"
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


def _build_visual_filters(
    scene: Scene,
    duration: float,
    is_first: bool,
    is_last: bool,
) -> str:
    """Compose the full visual filter chain for a scene."""

    filters = []

    # 1. Normalize image to fill 1920x1080 with proper padding.
    filters.append(
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0a0a1a"
    )

    # 2. Ken Burns (zoom / pan).
    frames = int(duration * FPS)
    frames = max(frames, 1)

    kb = {
        "zoom_in": "z='min(zoom+0.0015,1.3)'",
        "zoom_out": "z='if(lte(zoom,1.0),1.3,max(1.001,zoom-0.0015))'",
        "pan_left": "z='1.2':x='if(lte(on,1),iw/4,iw/4-on*2)':y='ih/4'",
        "pan_right": "z='1.2':x='if(lte(on,1),0,on*2)':y='ih/4'",
    }.get(
        scene.ken_burns,
        "z='min(zoom+0.0015,1.3)'",
    )

    filters.append(
        f"zoompan={kb}:d={frames}:s={RESOLUTION}:fps={FPS}"
    )

    # 3. Historical color grading.
    filters.append(
        "eq=saturation=0.85:contrast=1.05:brightness=-0.02,"
        "colorbalance=rs=0.05:gs=0.0:bs=-0.05"
    )

    # 4. Vignette.
    filters.append("vignette=PI/5")

    # 5. Fade in/out.
    if is_first:
        filters.append("fade=t=in:st=0:d=1.2")

    if is_last:
        filters.append(
            f"fade=t=out:st={max(duration - 1.2, 0):.2f}:d=1.2"
        )

    # 6. Final format.
    filters.append("format=yuv420p")

    return ",".join(filters)


def _ken_burns(
    image: str,
    duration: float,
    direction: str,
    out: str,
    is_first: bool = False,
    is_last: bool = False,
    fit_mode: str = "contain",
):
    frames = max(int(duration * FPS), 1)

    kb = {
        "zoom_in": "z='min(zoom+0.0015,1.3)'",
        "zoom_out": "z='if(lte(zoom,1.0),1.3,max(1.001,zoom-0.0015))'",
        "pan_left": "z='1.2':x='if(lte(on,1),iw/4,iw/4-on*2)':y='ih/4'",
        "pan_right": "z='1.2':x='if(lte(on,1),0,on*2)':y='ih/4'",
    }.get(
        direction,
        "z='min(zoom+0.0015,1.3)'",
    )

    # Fit mode.
    if fit_mode == "cover":
        scale_pad = (
            "scale=1920:1080:force_original_aspect_ratio=increase,"
            "crop=1920:1080"
        )
    else:
        scale_pad = (
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0a0a1a"
        )

    vf_parts = [
        scale_pad,
        f"zoompan={kb}:d={frames}:s={RESOLUTION}:fps={FPS}",
        "eq=saturation=0.92:contrast=1.05:brightness=-0.02",
        "vignette=PI/5",
    ]

    if is_first:
        vf_parts.append("fade=t=in:st=0:d=1.0")

    if is_last:
        vf_parts.append(
            f"fade=t=out:st={max(duration - 1.0, 0):.2f}:d=1.0"
        )

    vf_parts.append("format=yuv420p")

    # Images have no audio, so there is nothing to volume-control here.
    subprocess.run(
        [
            FFMPEG,
            "-y",
            "-loop",
            "1",
            "-i",
            image,
            "-vf",
            ",".join(vf_parts),
            "-t",
            str(duration),
            "-an",
            "-c:v",
            VIDEO_CODEC,
            "-preset",
            VIDEO_PRESET,
            "-crf",
            str(VIDEO_CRF),
            out,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _process_graphic_video(
    video: str,
    duration: float,
    out: str,
    is_first: bool = False,
    is_last: bool = False,
    fit_mode: str = "contain",
    volume: float = 1.0,
):
    """Process an already-rendered/downloaded video.

    The original audio is preserved when present and scaled by `volume`.
    Volume is 0.0–1.0.
    """

    if fit_mode == "cover":
        scale_pad = (
            "scale=1920:1080:force_original_aspect_ratio=increase,"
            "crop=1920:1080"
        )
    else:
        scale_pad = (
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0a0a1a"
        )

    vf_parts = [
        scale_pad,
        "eq=saturation=0.92:contrast=1.05:brightness=-0.02",
        "vignette=PI/5",
    ]

    if is_first:
        vf_parts.append("fade=t=in:st=0:d=1.0")

    if is_last:
        vf_parts.append(
            f"fade=t=out:st={max(duration - 1.0, 0):.2f}:d=1.0"
        )

    vf_parts.append("format=yuv420p")

    # Keep the source audio when available.
    # `volume=0` is valid and effectively mutes the clip.
    af = f"volume={volume:.4f}"

    subprocess.run(
        [
            FFMPEG,
            "-y",
            "-i",
            video,
            "-t",
            str(duration),
            "-vf",
            ",".join(vf_parts),
            "-af",
            af,
            "-c:v",
            VIDEO_CODEC,
            "-preset",
            VIDEO_PRESET,
            "-crf",
            str(VIDEO_CRF),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            out,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _trim_recording(
    video: str,
    start: float,
    duration: float,
    out: str,
    is_first: bool = False,
    is_last: bool = False,
    volume: float = 1.0,
):
    """Trim and apply light effects to a recording segment.

    Recording audio is preserved and controlled by `volume`.
    """

    vf_parts = [
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0a0a1a",
        "eq=saturation=0.95:contrast=1.02",
    ]

    if is_first:
        vf_parts.append("fade=t=in:st=0:d=1.0")

    if is_last:
        vf_parts.append(
            f"fade=t=out:st={max(duration - 1.0, 0):.2f}:d=1.0"
        )

    vf_parts.append("format=yuv420p")

    subprocess.run(
        [
            FFMPEG,
            "-y",
            "-ss",
            str(start),
            "-i",
            video,
            "-t",
            str(duration),
            "-vf",
            ",".join(vf_parts),
            "-af",
            f"volume={volume:.4f}",
            "-c:v",
            VIDEO_CODEC,
            "-preset",
            VIDEO_PRESET,
            "-crf",
            str(VIDEO_CRF),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            out,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _placeholder(
    duration: float,
    out: str,
    is_first: bool = False,
    is_last: bool = False,
):
    vf_parts = ["format=yuv420p"]

    if is_first:
        vf_parts.insert(
            0,
            "fade=t=in:st=0:d=1.0",
        )

    if is_last:
        vf_parts.insert(
            0,
            f"fade=t=out:st={max(duration - 1.0, 0):.2f}:d=1.0",
        )

    subprocess.run(
        [
            FFMPEG,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x0a0a1a:s={RESOLUTION}:d={duration}:r={FPS}",
            "-vf",
            ",".join(vf_parts),
            "-c:v",
            VIDEO_CODEC,
            "-preset",
            "ultrafast",
            "-crf",
            "28",
            "-an",
            out,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
