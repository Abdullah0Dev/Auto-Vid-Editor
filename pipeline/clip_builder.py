"""Build per-scene clips with Ken Burns, effects, and animations."""
import subprocess
from pathlib import Path

from config import (
    FFMPEG, FPS, RESOLUTION, VIDEO_CODEC, VIDEO_PRESET,
    VIDEO_CRF, CLIPS_DIR,
)
from models.types import Scene
from utils.logger import log


def build_all(video_path: str, scenes: list[Scene]) -> list[str]:
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, scene in enumerate(scenes):
        out = str(CLIPS_DIR / f"clip_{scene.id:03d}.mp4")
        _build_one(video_path, scene, out, is_first=(i == 0),
                   is_last=(i == len(scenes) - 1))
        paths.append(out)
    log.ok(f"{len(paths)} clips built")
    return paths


def _build_one(video_path: str, scene: Scene, out: str,
               is_first: bool = False, is_last: bool = False):
    duration = scene.end - scene.start

    if scene.visual_type == "recording":
        _trim_recording(video_path, scene.start, duration, out,
                        is_first, is_last)
    elif scene.chosen_asset:
        _ken_burns(scene.chosen_asset, duration, scene.ken_burns, out,
                   is_first, is_last)
    else:
        _placeholder(duration, out, is_first, is_last)


def _build_visual_filters(scene: Scene, duration: float,
                          is_first: bool, is_last: bool) -> str:
    """Compose the full visual filter chain for a scene."""
    filters = []

    # 1. Normalize image to fill 1920x1080 with proper padding
    filters.append(
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0a0a1a"
    )

    # 2. Ken Burns (zoom / pan)
    frames = int(duration * FPS)
    frames = max(frames, 1)  # safety
    kb = {
        "zoom_in":     "z='min(zoom+0.0015,1.3)'",
        "zoom_out":    "z='if(lte(zoom,1.0),1.3,max(1.001,zoom-0.0015))'",
        "pan_left":    "z='1.2':x='if(lte(on,1),iw/4,iw/4-on*2)':y='ih/4'",
        "pan_right":   "z='1.2':x='if(lte(on,1),0,on*2)':y='ih/4'",
    }.get(scene.ken_burns, "z='min(zoom+0.0015,1.3)'")
    filters.append(f"zoompan={kb}:d={frames}:s={RESOLUTION}:fps={FPS}")

    # 3. Historical color grading (subtle sepia warmth)
    filters.append(
        "eq=saturation=0.85:contrast=1.05:brightness=-0.02,"
        "colorbalance=rs=0.05:gs=0.0:bs=-0.05"
    )

    # 4. Vignette (cinematic edges)
    filters.append("vignette=PI/5")

    # 5. Fade in/out — only on the very first and very last clip
    if is_first:
        filters.append("fade=t=in:st=0:d=1.2")
    if is_last:
        filters.append(f"fade=t=out:st={max(duration - 1.2, 0):.2f}:d=1.2")

    # 6. Final format
    filters.append("format=yuv420p")

    return ",".join(filters)


def _ken_burns(image: str, duration: float, direction: str, out: str,
               is_first: bool = False, is_last: bool = False):
    # Build a dummy Scene-like object for filter building
    class _S: pass
    s = _S()
    s.ken_burns = direction
    vf = _build_visual_filters(s, duration, is_first, is_last)

    subprocess.run([
        FFMPEG, "-y", "-loop", "1", "-i", image,
        "-vf", vf,
        "-t", str(duration),
        "-c:v", VIDEO_CODEC, "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
        out,
    ], check=True, capture_output=True, text=True)


def _trim_recording(video: str, start: float, duration: float, out: str,
                    is_first: bool = False, is_last: bool = False):
    """Trim and apply light effects to a recording segment."""
    vf_parts = [
        f"scale=1920:1080:force_original_aspect_ratio=decrease,"
        f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0a0a1a",
        "eq=saturation=0.95:contrast=1.02",
    ]
    if is_first:
        vf_parts.append("fade=t=in:st=0:d=1.0")
    if is_last:
        vf_parts.append(f"fade=t=out:st={max(duration - 1.0, 0):.2f}:d=1.0")
    vf_parts.append("format=yuv420p")

    subprocess.run([
        FFMPEG, "-y", "-ss", str(start), "-i", video, "-t", str(duration),
        "-vf", ",".join(vf_parts),
        "-c:v", VIDEO_CODEC, "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
        "-an", out,
    ], check=True, capture_output=True, text=True)


def _placeholder(duration: float, out: str,
                 is_first: bool = False, is_last: bool = False):
    vf_parts = ["format=yuv420p"]
    if is_first:
        vf_parts.insert(0, "fade=t=in:st=0:d=1.0")
    if is_last:
        vf_parts.insert(0, f"fade=t=out:st={max(duration - 1.0, 0):.2f}:d=1.0")

    subprocess.run([
        FFMPEG, "-y", "-f", "lavfi",
        "-i", f"color=c=0x0a0a1a:s={RESOLUTION}:d={duration}:r={FPS}",
        "-vf", ",".join(vf_parts),
        "-c:v", VIDEO_CODEC, "-preset", "ultrafast", "-crf", "28", out,
    ], check=True, capture_output=True, text=True)