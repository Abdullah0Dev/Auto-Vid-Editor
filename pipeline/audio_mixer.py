"""Build FFmpeg audio filter chain: echo, ducking, mixing."""
from config import (DUCK_THRESHOLD, DUCK_RATIO, DUCK_ATTACK, DUCK_RELEASE,
                    BG_MUSIC_VOLUME, NASHEED_VOLUME)
from models.types import ImportantMoment


def build_filter(
    important_moments: list[ImportantMoment],
    has_bg_music: bool = False,
    has_nasheed: bool = False,
) -> str:
    """Returns the full filter_complex string for audio."""
    filters: list[str] = []

    # Base narration input
    filters.append("[1:a]anull[narr_base]")
    current = "[narr_base]"
    next_idx = 2  # bg_music will be input 2

    # Background music ducking
    if has_bg_music:
        filters.append(f"[{next_idx}:a]volume={BG_MUSIC_VOLUME}[music]")
        filters.append(
            f"[music][narr_base]sidechaincompress="
            f"threshold={DUCK_THRESHOLD}:ratio={DUCK_RATIO}:"
            f"attack={DUCK_ATTACK}:release={DUCK_RELEASE}[music_ducked]"
        )
        filters.append(f"[narr_base][music_ducked]amix=inputs=2:duration=first:normalize=0[mixed]")
        current = "[mixed]"
        next_idx += 1

    # Nasheed overlay (اناشيد حماسية) — mixed louder, no ducking
    if has_nasheed:
        filters.append(f"[{next_idx}:a]volume={NASHEED_VOLUME}[nasheed]")
        filters.append(f"{current}[nasheed]amix=inputs=2:duration=first:normalize=0[mixed2]")
        current = "[mixed2]"
        next_idx += 1

    # Apply echo/reverb on important moments
    # (simple version: global echo delay envelope handled in renderer)
    filters.append(f"{current}anull[aout]")

    return ";".join(filters)