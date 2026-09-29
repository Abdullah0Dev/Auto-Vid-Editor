"""Step 1 — Arabic transcription using mlx-whisper (Apple Silicon optimized)."""

import mlx_whisper
from pathlib import Path

from config import (
    WHISPER_MODEL,
    WHISPER_LANGUAGE,
    WHISPER_TEMPERATURE,
    TRANSCRIPT_DIR,
)
from models.types import TranscriptSegment
from utils.logger import log


def transcribe(video_path: str) -> list[TranscriptSegment]:
    """
    Transcribe Arabic audio directly from an MP4 using mlx-whisper.

    mlx-whisper runs on Apple Silicon's GPU via MLX and decodes MP4
    internally through ffmpeg — no manual WAV extraction needed.
    """
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)

    log.info(f"Transcribing {Path(video_path).name} with MLX on Apple GPU...")

    result = mlx_whisper.transcribe(
        video_path,
        path_or_hf_repo=WHISPER_MODEL,
        language=WHISPER_LANGUAGE,
        temperature=WHISPER_TEMPERATURE,
        word_timestamps=False,
    )

    segments = [
        TranscriptSegment(
            start=float(seg["start"]),
            end=float(seg["end"]),
            text=seg["text"].strip(),
        )
        for seg in result.get("segments", [])
        if seg.get("text", "").strip()
    ]

    # Save raw output for debugging
    out_json = TRANSCRIPT_DIR / "transcript.json"
    import json
    out_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    log.ok(f"{len(segments)} segments transcribed")
    dur = get_video_duration(video_path)
    if segments:
        last_end = max(s.end for s in segments)
        log.info(f"Video duration: {dur:.1f}s | "
                 f"Transcript covers: 0.0s–{last_end:.1f}s")
        if dur - last_end > 2.0:
            log.warn(f"⚠ Whisper stopped {dur - last_end:.1f}s before "
                     f"end of video — scenes will be extended to cover it")
    return segments


def to_timestamped_text(segments: list[TranscriptSegment]) -> str:
    return "\n".join(f"[{s.start:.1f}–{s.end:.1f}] {s.text}" for s in segments)

def get_video_duration(video_path: str) -> float:
    """Return duration of a video file in seconds. 0.0 if unknown."""
    import subprocess
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0