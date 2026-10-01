"""Local semantic B-roll asset source.

Searches the reusable video catalog using:
    BGE-M3 + sqlite-vec

The database stores metadata and embeddings.
Actual videos live under VECTOR_CLIPS_DIR.
"""

from __future__ import annotations

from pathlib import Path

from config import (
    VECTOR_CLIPS_DIR,
    VECTOR_DB_PATH,
    VECTOR_ENABLED,
    VECTOR_MAX_DISTANCE,
    VECTOR_MODEL_NAME,
    VECTOR_TOP_K,
)
from utils.logger import log


# ===============================================================
# Optional dependencies
# ===============================================================

try:
    import sqlean as sqlite3
    import sqlite_vec
    from sentence_transformers import SentenceTransformer

    _AVAILABLE = True

except ImportError:
    _AVAILABLE = False

    log.warn(
        "Vector source unavailable — "
        "install sqlean, sqlite-vec and sentence-transformers"
    )


# ===============================================================
# Cached model
# ===============================================================

_model = None


def _get_model():
    global _model

    if _model is None and _AVAILABLE and VECTOR_ENABLED:

        log.info(
            f"Loading BGE model ({VECTOR_MODEL_NAME})..."
        )

        _model = SentenceTransformer(
            VECTOR_MODEL_NAME
        )

        log.ok("BGE-M3 loaded")

    return _model


# ===============================================================
# Public API
# ===============================================================

def search(
    query: str,
    top_k: int = VECTOR_TOP_K,
) -> list[str]:

    if not VECTOR_ENABLED:
        return []

    if not _AVAILABLE:
        return []

    if not query.strip():
        return []

    if not VECTOR_DB_PATH.exists():
        log.warn(
            f"Vector DB not found: {VECTOR_DB_PATH}"
        )
        return []

    model = _get_model()

    if model is None:
        return []

    try:

        # -------------------------------------------------------
        # Encode query
        # -------------------------------------------------------

        embedding = model.encode(
            query,
            normalize_embeddings=True,
        ).astype("float32").tolist()

        # -------------------------------------------------------
        # Open DB
        # -------------------------------------------------------

        db = sqlite3.connect(
            str(VECTOR_DB_PATH)
        )

        try:

            db.enable_load_extension(True)

            sqlite_vec.load(db)

            db.enable_load_extension(False)

            rows = db.execute(
                """
                SELECT
                    c.source_id,
                    c.path,
                    c.caption_ar,
                    vec_distance_cosine(
                        v.text_embedding,
                        ?
                    ) AS distance
                FROM clips_vec v
                JOIN clips c
                    ON c.id = v.clip_id
                ORDER BY distance
                LIMIT ?
                """,
                (
                    sqlite_vec.serialize_float32(
                        embedding
                    ),
                    top_k,
                ),
            ).fetchall()

        finally:
            db.close()

        # -------------------------------------------------------
        # Resolve / validate assets
        # -------------------------------------------------------

        results: list[str] = []

        for source_id, db_path, caption_ar, distance in rows:

            if distance > VECTOR_MAX_DISTANCE:
                continue

            asset = _resolve_asset(db_path)

            if asset is None:
                log.warn(
                    f"[vector] missing asset "
                    f"{source_id}: {db_path}"
                )
                continue

            results.append(str(asset))

            log.info(
                f"[vector] {source_id} "
                f"d={distance:.3f} "
                f"→ {asset.name}"
            )

        if results:

            log.ok(
                f"[vector] {len(results)} "
                f"relevant B-roll asset(s)"
            )

        else:

            log.info(
                "[vector] no sufficiently relevant matches"
            )

        return results

    except Exception as e:

        log.warn(
            f"[vector] search failed: {e}"
        )

        return []


# ===============================================================
# Path resolution
# ===============================================================

def _resolve_asset(db_path: str) -> Path | None:

    if not db_path:
        return None

    original = Path(db_path)

    # -----------------------------------------------------------
    # 1. Current DB path still works
    # -----------------------------------------------------------

    if original.exists():
        return original

    # -----------------------------------------------------------
    # 2. Use filename against our local clips directory
    # -----------------------------------------------------------

    local = VECTOR_CLIPS_DIR / original.name

    if local.exists():
        return local

    return None