"""Build FFmpeg audio filter chain with per-content-type effects.

Detects scenes marked as quran/hadith/poetry/dua and applies a
mosque-acoustic / echo effect to those segments while leaving
regular narration untouched.
"""
from config import (
    DUCK_THRESHOLD, DUCK_RATIO, DUCK_ATTACK, DUCK_RELEASE,
    BG_MUSIC_VOLUME, NASHEED_VOLUME,
)
from models.types import Scene, ImportantMoment
from utils.logger import log


# Per-content-type effects.
# Each value is a filter chain applied AFTER atrim/asetpts.
# aecho: in_gain:out_gain:delays|delays:decays|decays
CONTENT_TYPE_EFFECTS: dict[str, str | None] = {
    "narration": None,   # pass-through
    "quran":     "aecho=0.65:0.85:120|240:0.35|0.20,volume=0.90",
    "hadith":    "aecho=0.65:0.85:90|180:0.30|0.15,volume=0.92",
    "poetry":    "aecho=0.70:0.90:50|100|150:0.30|0.20|0.10,volume=0.95",
    "dua":       "aecho=0.55:0.80:200|400:0.40|0.25,volume=0.85",
}


def build_filter(
    scenes: list[Scene] | None = None,
    important_moments: list[ImportantMoment] | None = None,
    has_bg_music: bool = False,
    has_nasheed: bool = False,
) -> str:
    """
    Build the complete audio filter.

    Inputs (in the final mux):
      [0:v]  = concatenated video
      [1:a]  = original narration (full recording audio)
      [2:a]  = bg_music (if has_bg_music)
      [3:a]  = nasheed (if has_nasheed)

    Output:
      [aout] = final mixed audio
    """
    scenes = scenes or []
    important_moments = important_moments or []
    filters: list[str] = []

    # ── 1. Split narration into scene-aligned segments and apply effects
    narration_label = _build_scene_audio_chain(scenes, filters)

    # ── 2. Duck background music under the narration
    current = narration_label
    next_input = 2

    if has_bg_music:
        filters.append(f"[{next_input}:a]volume={BG_MUSIC_VOLUME}[music]")
        filters.append(
            f"[music][{current}]sidechaincompress="
            f"threshold={DUCK_THRESHOLD}:ratio={DUCK_RATIO}:"
            f"attack={DUCK_ATTACK}:release={DUCK_RELEASE}[music_ducked]"
        )
        filters.append(
            f"[{current}][music_ducked]"
            f"amix=inputs=2:duration=first:normalize=0[mixed]"
        )
        current = "mixed"
        next_input += 1

    # ── 3. Mix in nasheed for حماسه moments (less ducked)
    if has_nasheed:
        filters.append(f"[{next_input}:a]volume={NASHEED_VOLUME}[nasheed]")
        filters.append(
            f"[{current}][nasheed]"
            f"amix=inputs=2:duration=first:normalize=0[mixed2]"
        )
        current = "mixed2"

    # ── 4. Tag important moments (for future per-timestamp effects)
    if important_moments:
        log.info(f"Audio: {len(important_moments)} important moment(s) "
                 f"(echo injection is a future upgrade)")

    filters.append(f"[{current}]anull[aout]")
    return ";".join(filters)


def _build_scene_audio_chain(scenes: list[Scene],
                              filters: list[str]) -> str:
    """
    Split [1:a] (narration) into scene-timed segments, apply per-type
    effects to special ones, concatenate back to a single stream.

    Returns the label of the resulting stream (without brackets).
    """
    if not scenes:
        filters.append("[1:a]anull[narr]")
        return "narr"

    sorted_scenes = sorted(scenes, key=lambda s: s.start)

    # Build segments, filling gaps with pass-through narration
    segments: list[tuple[float, float, str | None]] = []
    prev_end = 0.0

    for scene in sorted_scenes:
        # Gap before this scene
        if scene.start > prev_end + 0.01:
            segments.append((prev_end, scene.start, None))

        # Safe attribute access — Scene always has content_type now,
        # but this guards against older pickled scenes or edge cases.
        ctype = getattr(scene, "content_type", "narration") or "narration"
        effect = CONTENT_TYPE_EFFECTS.get(ctype)

        segments.append((scene.start, scene.end, effect))
        prev_end = max(prev_end, scene.end)

    # If nothing is special, skip the split/rebuild entirely
    if not any(effect for _, _, effect in segments):
        log.info("Audio: no quran/hadith/poetry/dua scenes — narration passes through")
        filters.append("[1:a]anull[narr]")
        return "narr"

    special = sum(1 for _, _, e in segments if e)
    log.info(f"Audio: {special} special segment(s), "
             f"{len(segments) - special} narration segment(s)")

    labels: list[str] = []

    for i, (start, end, effect) in enumerate(segments):
        duration = end - start
        if duration <= 0.01:
            continue

        seg_label = f"seg{i}"
        proc_label = f"proc{i}"

        filters.append(
            f"[1:a]atrim=start={start:.3f}:end={end:.3f},"
            f"asetpts=PTS-STARTPTS[{seg_label}]"
        )

        if effect:
            filters.append(f"[{seg_label}]{effect}[{proc_label}]")
        else:
            filters.append(f"[{seg_label}]anull[{proc_label}]")

        labels.append(f"[{proc_label}]")

    if not labels:
        filters.append("[1:a]anull[narr]")
        return "narr"

    filters.append(
        f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1[narr]"
    )
    return "narr"