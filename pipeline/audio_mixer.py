"""Build FFmpeg audio filter chain with per-content-type effects.

Detects scenes marked as quran/hadith/poetry/dua and applies a
mosque-acoustic / echo effect to those segments while leaving
regular narration untouched.

Audio segments are kept aligned to their original timeline.
"""

from config import (
    DUCK_THRESHOLD,
    DUCK_RATIO,
    DUCK_ATTACK,
    DUCK_RELEASE,
    BG_MUSIC_VOLUME,
    NASHEED_VOLUME,
)

from models.types import Scene, ImportantMoment
from utils.logger import log


CONTENT_TYPE_EFFECTS: dict[str, str | None] = {
    "narration": None,
    "quran": "aecho=0.65:0.85:120|240:0.35|0.20,volume=0.90",
    "hadith": "aecho=0.65:0.85:90|180:0.30|0.15,volume=0.92",
    "poetry": "aecho=0.70:0.90:50|100|150:0.30|0.20|0.10,volume=0.95",
    "dua": "aecho=0.55:0.80:200|400:0.40|0.25,volume=0.85",
}


def build_filter(
    scenes: list[Scene] | None = None,
    important_moments: list[ImportantMoment] | None = None,
    has_bg_music: bool = False,
    has_nasheed: bool = False,
) -> str:
    """Build the complete final audio filter graph."""

    scenes = scenes or []
    important_moments = important_moments or []

    filters: list[str] = []

    narration_label = _build_scene_audio_chain(
        scenes,
        filters,
    )

    current = narration_label
    next_input = 2

    # Background music with narration-driven ducking.
    if has_bg_music:
        filters.append(
            f"[{next_input}:a]"
            f"volume={BG_MUSIC_VOLUME}[music]"
        )

        filters.append(
            f"[music][{current}]"
            f"sidechaincompress="
            f"threshold={DUCK_THRESHOLD}:"
            f"ratio={DUCK_RATIO}:"
            f"attack={DUCK_ATTACK}:"
            f"release={DUCK_RELEASE}"
            f"[music_ducked]"
        )

        filters.append(
            f"[{current}][music_ducked]"
            f"amix=inputs=2:duration=first:normalize=0"
            f"[mixed]"
        )

        current = "mixed"
        next_input += 1

    # Nasheed.
    if has_nasheed:
        filters.append(
            f"[{next_input}:a]"
            f"volume={NASHEED_VOLUME}[nasheed]"
        )

        filters.append(
            f"[{current}][nasheed]"
            f"amix=inputs=2:duration=first:normalize=0"
            f"[mixed2]"
        )

        current = "mixed2"

    if important_moments:
        log.info(
            f"Audio: {len(important_moments)} important moment(s)"
        )

    filters.append(
        f"[{current}]anull[aout]"
    )

    return ";".join(filters)


def _build_scene_audio_chain(
    scenes: list[Scene],
    filters: list[str],
) -> str:
    """Build scene-aligned narration segments."""

    if not scenes:
        filters.append(
            "[1:a]anull[narr]"
        )
        return "narr"

    sorted_scenes = sorted(
        scenes,
        key=lambda scene: scene.start,
    )

    segments: list[tuple[float, float, str | None]] = []

    prev_end = 0.0

    for scene in sorted_scenes:
        start = max(float(scene.start), 0.0)
        end = max(float(scene.end), start)

        if end <= start:
            continue

        # Preserve narration in gaps.
        if start > prev_end + 0.01:
            segments.append(
                (prev_end, start, None)
            )

        content_type = (
            getattr(scene, "content_type", "narration")
            or "narration"
        )

        effect = CONTENT_TYPE_EFFECTS.get(
            content_type
        )

        # Handle overlapping scene boundaries safely.
        start = max(start, prev_end)

        if end > start:
            segments.append(
                (start, end, effect)
            )

        prev_end = max(prev_end, end)

    if not segments:
        filters.append(
            "[1:a]anull[narr]"
        )
        return "narr"

    if not any(effect for _, _, effect in segments):
        log.info(
            "Audio: no special content effects — narration passes through"
        )

        filters.append(
            "[1:a]anull[narr]"
        )

        return "narr"

    special_count = sum(
        1 for _, _, effect in segments if effect
    )

    log.info(
        f"Audio: {special_count} special segment(s), "
        f"{len(segments) - special_count} regular segment(s)"
    )

    labels: list[str] = []

    for i, (start, end, effect) in enumerate(segments):
        duration = end - start

        if duration <= 0.01:
            continue

        seg_label = f"seg{i}"
        proc_label = f"proc{i}"

        # Extract original narration at the exact timeline position.
        filters.append(
            f"[1:a]"
            f"atrim=start={start:.6f}:end={end:.6f},"
            f"asetpts=PTS-STARTPTS"
            f"[{seg_label}]"
        )

        if effect:
            # Apply the effect, then constrain the output to the
            # original scene duration so echo tails cannot shift
            # the next narration segment.
            filters.append(
                f"[{seg_label}]"
                f"{effect},"
                f"atrim=duration={duration:.6f},"
                f"asetpts=PTS-STARTPTS"
                f"[{proc_label}]"
            )
        else:
            filters.append(
                f"[{seg_label}]"
                f"atrim=duration={duration:.6f},"
                f"asetpts=PTS-STARTPTS"
                f"[{proc_label}]"
            )

        labels.append(
            f"[{proc_label}]"
        )

    if not labels:
        filters.append(
            "[1:a]anull[narr]"
        )
        return "narr"

    filters.append(
        f"{''.join(labels)}"
        f"concat=n={len(labels)}:v=0:a=1"
        f"[narr]"
    )

    return "narr"
