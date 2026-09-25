"""Analyze loudness over time using FFmpeg ebur128."""
import re
import subprocess

from config import FFMPEG
from models.types import LoudnessSample
from utils.logger import log


# ebur128=verbose output (per frame):
#   [Parsed_ebur128_0 @ 0x...] t: 0.10  M: -23.9  S: -120.7  I: -23.9  LUFS  LRA: 0.0
LINE_RE = re.compile(r"t:\s*([\d.]+)\s+M:\s*(-?[\d.]+|-inf)")


def analyze(video_path: str) -> list[LoudnessSample]:
    log.info("Analyzing audio loudness...")

    # Note: do NOT add -nostats or -hide_banner — they suppress the
    # per-frame ebur128 output we need.
    cmd = [
        FFMPEG, "-i", video_path,
        "-af", "ebur128=metadata=1:framelog=verbose",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    samples: list[LoudnessSample] = []
    for line in result.stderr.split("\n"):
        m = LINE_RE.search(line)
        if not m:
            continue
        try:
            t = float(m.group(1))
            m_val = m.group(2)
            loudness = -70.0 if m_val == "-inf" else float(m_val)
            samples.append(LoudnessSample(time=t, loudness=loudness))
        except ValueError:
            continue

    if samples:
        log.ok(f"{len(samples)} loudness samples")
    else:
        log.warn("No loudness samples extracted — check FFmpeg output")
        # Print a small slice of stderr so we can see the actual format
        sample_lines = [
            l for l in result.stderr.split("\n")
            if "ebur128" in l or "Parsed" in l
        ]
        for line in sample_lines[:3]:
            log.warn(f"  sample line: {line[:150]}")

    return samples