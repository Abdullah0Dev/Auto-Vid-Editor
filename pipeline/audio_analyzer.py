"""Analyze loudness over time using FFmpeg ebur128."""
import subprocess

from config import FFMPEG
from models.types import LoudnessSample
from utils.logger import log


def analyze(video_path: str) -> list[LoudnessSample]:
    log.info("Analyzing audio loudness...")

    result = subprocess.run(
        [
            FFMPEG, "-i", video_path,
            "-af", "ebur128=metadata=1:framelog=verbose",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )

    samples: list[LoudnessSample] = []
    for line in result.stderr.split("\n"):
        if "t:" in line and "M:" in line:
            try:
                parts = line.split()
                t = float([p for p in parts if p.startswith("t:")][0].split(":")[1])
                m = float([p for p in parts if p.startswith("M:")][0].split(":")[1])
                samples.append(LoudnessSample(time=t, loudness=m))
            except (IndexError, ValueError):
                continue

    log.ok(f"{len(samples)} loudness samples")
    return samples