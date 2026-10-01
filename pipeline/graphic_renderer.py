"""Renders Remotion compositions and returns local mp4/mov paths."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from config import (
    GRAPHIC_CACHE_DIR,
    GRAPHIC_FPS,
    REMOTION_DIR,
)
from utils.logger import log


# =============================================================================
# Public
# =============================================================================

def render_graphic(
    template: str,
    props: dict,
    duration_seconds: float,
    transparent: bool = False,
) -> Path:
    """Render one graphic. Returns the local rendered file path."""

    GRAPHIC_CACHE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # -------------------------------------------------------------------------
    # Duration
    # -------------------------------------------------------------------------

    duration_frames = max(
        1,
        round(
            duration_seconds * GRAPHIC_FPS
        ),
    )

    # -------------------------------------------------------------------------
    # Build deterministic cache key
    # -------------------------------------------------------------------------

    merged_props = {
        **props,
        "durationInFrames": duration_frames,
    }

    payload = {
        "template": template,
        "props": merged_props,
        "durationInFrames": duration_frames,
        "transparent": transparent,
    }

    key = hashlib.md5(
        json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()

    ext = "mov" if transparent else "mp4"

    out = (
        GRAPHIC_CACHE_DIR /
        f"{key}.{ext}"
    ).resolve()

    # -------------------------------------------------------------------------
    # Cache hit
    # -------------------------------------------------------------------------

    if (
        out.exists()
        and out.stat().st_size > 10_000
    ):
        log.info(
            f"  [remotion] cache hit → {out.name}"
        )
        return out

    # -------------------------------------------------------------------------
    # Props file
    # -------------------------------------------------------------------------

    props_file = (
        GRAPHIC_CACHE_DIR /
        f"{key}.json"
    ).resolve()

    props_file.write_text(
        json.dumps(
            merged_props,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # -------------------------------------------------------------------------
    # IMPORTANT:
    #
    # Pass the actual Remotion entry point to `render`.
    #
    # Do NOT pass:
    #   cache/graphics/_bundle
    #
    # Do NOT host the bundle through a homemade HTTP server.
    #
    # Remotion will bundle the entry point itself and use its normal
    # Webpack cache.
    # -------------------------------------------------------------------------

    index_ts = (
        REMOTION_DIR /
        "src" /
        "index.ts"
    ).resolve()

    if not index_ts.is_file():
        raise RuntimeError(
            f"Remotion entry point not found: {index_ts}"
        )

    # -------------------------------------------------------------------------
    # Normalize planner template -> actual Composition ID
    # -------------------------------------------------------------------------

    composition_id = _composition_id(
        template
    )

    cmd = [
        "npx",
        "remotion",
        "render",

        # Absolute entry point.
        str(index_ts),

        # Composition registered by Root.tsx.
        composition_id,

        # Absolute output path.
        str(out),

        # Runtime props.
        f"--props={props_file}",

        # Let Remotion handle its own bundle caching.
        "--bundle-cache=true",

        # Concurrency.
        f"--concurrency={_cpu_concurrency()}",
    ]

    if transparent:
        cmd += [
            "--codec=prores",
            "--prores-profile=4444",
            "--pixel-format=yuva444p10le",
            "--image-format=png",
        ]

    log.info(
        f"  [remotion] rendering "
        f"{template} → {composition_id} "
        f"({duration_frames}f) → {out.name}"
    )

    # -------------------------------------------------------------------------
    # Render
    # -------------------------------------------------------------------------

    try:
        result = subprocess.run(
            cmd,
            cwd=REMOTION_DIR.resolve(),
            capture_output=True,
            text=True,
            timeout=300,
        )

    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Remotion render timed out for {template}"
        ) from exc

    # -------------------------------------------------------------------------
    # Failure
    # -------------------------------------------------------------------------

    if result.returncode != 0:
        if result.stdout:
            log.warn(
                result.stdout[-2000:]
            )

        if result.stderr:
            log.warn(
                result.stderr[-2000:]
            )

        raise RuntimeError(
            f"Remotion render failed "
            f"(exit {result.returncode})"
        )

    # -------------------------------------------------------------------------
    # Validate output
    # -------------------------------------------------------------------------

    if (
        not out.exists()
        or out.stat().st_size < 10_000
    ):
        raise RuntimeError(
            "Remotion produced an empty output"
        )

    log.ok(
        f"  [remotion] {out.name} "
        f"({out.stat().st_size // 1024} KB)"
    )

    return out


# =============================================================================
# Composition ID mapping
# =============================================================================

def _composition_id(
    template: str,
) -> str:
    """
    Convert pipeline template IDs into the actual Remotion composition IDs.

    Root.tsx currently converts underscores to hyphens.
    """

    aliases = {
        # Current planner name -> registry name.
        "islamic_map": "map",
    }

    normalized = aliases.get(
        template,
        template,
    )

    return normalized.replace(
        "_",
        "-",
    )


# =============================================================================
# CPU concurrency
# =============================================================================

def _cpu_concurrency() -> str:
    n = os.cpu_count() or 4

    return (
        "50%"
        if n >= 8
        else str(max(2, n - 1))
    )