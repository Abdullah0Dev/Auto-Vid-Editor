"""Analyze loudness over time using FFmpeg ebur128."""
import re
import subprocess

from config import FFMPEG
from models.types import LoudnessSample
from utils.logger import log


# Parse the ebur128 verbose log line, which looks like:
#   [Parsed_ebur128_0 @ 0x...] t: 0.10  M: -23.9  S: -120.7  I: -23.9 LUFS  LRA: 0.0
# OR
#   t: 0.10  M: -23.9
LINE_RE = re.compile(r"t:\s*([\d.]+)\s+M:\s*(-?[\d.]+|-inf)")


def analyze(video_path: str) -> list[LoudnessSample]:
    log.info("Analyzing audio loudness...")

    cmd = [
        FFMPEG,
        "-nostdin",
        "-i", video_path,
        "-af", "ebur128=framelog=verbose",
        "-f", "null",
        "-",
    ]

    # ebur128 verbose output goes to stderr. We need to capture it.
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        errors="ignore",
    )

    samples: list[LoudnessSample] = []
    for line in result.stderr.split("\n"):
        m = LINE_RE.search(line)
        if not m:
            continue
        try:
            t = float(m.group(1))
            val = m.group(2)
            loudness = -70.0 if val == "-inf" else float(val)
            samples.append(LoudnessSample(time=t, loudness=loudness))
        except ValueError:
            continue

    if samples:
        log.ok(f"{len(samples)} loudness samples "
               f"(range: {min(s.loudness for s in samples):.1f} "
               f"to {max(s.loudness for s in samples):.1f} LUFS)")
    else:
        log.warn("No loudness samples extracted — audio analysis is optional")
        # Try a raw check: does this video even have audio?
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=codec_type", "-of",
             "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True,
        )
        if "audio" not in probe.stdout:
            log.warn("  → No audio stream found in the video")
        else:
            log.warn("  → Audio exists; ebur128 parsing needs adjustment")

    return samples