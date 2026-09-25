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
    return segments


def to_timestamped_text(segments: list[TranscriptSegment]) -> str:
    return "\n".join(f"[{s.start:.1f}–{s.end:.1f}] {s.text}" for s in segments)