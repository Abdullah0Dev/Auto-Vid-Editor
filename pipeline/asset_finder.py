"""Step 5 — Find candidate visual assets for each scene.

Source priority:
    1. Local semantic B-roll catalog (BGE-M3 + sqlite-vec)
    2. Pinterest (Playwright — real web UI)
    3. Wikimedia Commons

Vector B-roll:
    - Returns existing reusable .mp4 assets directly.
    - No downloading/copying.
    - Returns ALL relevant matches from the vector source.

Image sources:
    - Download candidates into the scene workspace.
    - CLIP relevance filtering.
    - Perceptual-hash deduplication.
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
from urllib.parse import quote_plus

import requests

from config import (
    SCENE_ASSETS_DIR,
    WORKSPACE_DIR,

    SEARCH_QUERY_PREFERENCE,
    SEARCH_FALLBACK_TO_ENGLISH,

    PINTEREST_NUM_IMAGES,
    PINTEREST_MIN_RESOLUTION,
    PINTEREST_SCROLL_ROUNDS,
    PINTEREST_COOKIES_FILE,
    PINTEREST_HEADLESS,

    ENABLE_CLIP_FILTER,
    CLIP_MODEL_NAME,
    CLIP_MIN_SIMILARITY,
    CLIP_TOP_K,

    ENABLE_PHASH_DEDUP,
    PHASH_HAMMING_THRESHOLD,

    WIKIMEDIA_RESULT_COUNT,
    WIKIMEDIA_MIN_WIDTH,
    WIKIMEDIA_MIN_HEIGHT,
)

from models.types import Scene
from utils.logger import log

# Local semantic B-roll source.
#
# asset_sources/__init__.py should expose:
#
#     from .vector_source import search as search_vector
#
from pipeline.asset_sources import search_vector


# ===============================================================
# Optional imports
# ===============================================================

try:
    from playwright.async_api import async_playwright

    _PW_AVAILABLE = True

except ImportError:
    _PW_AVAILABLE = False

    log.warn(
        "playwright not installed — "
        "run: pip install playwright && playwright install chromium"
    )


try:
    from PIL import Image

    _PIL_AVAILABLE = True

except ImportError:
    _PIL_AVAILABLE = False


try:
    from sentence_transformers import SentenceTransformer

    _CLIP_AVAILABLE = True

except ImportError:
    _CLIP_AVAILABLE = False

    log.warn(
        "CLIP deps missing — "
        "run: pip install sentence-transformers torch"
    )


try:
    import imagehash

    _PHASH_AVAILABLE = True

except ImportError:
    _PHASH_AVAILABLE = False


# ===============================================================
# Constants
# ===============================================================

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"

USER_AGENT = (
    "ArabicVideoEditor/1.0 "
    "(local pipeline; contact: dev@localhost) "
    "python-requests/2.x"
)

_HEADERS = {
    "User-Agent": USER_AGENT,
}

_MIN_DELAY_WIKI = 1.0
_MAX_RETRIES = 3

_IMG_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}

_VIDEO_EXTS = {
    ".mp4",
    ".mov",
    ".webm",
    ".m4v",
}

STOP_WORDS = {
    "the",
    "a",
    "an",
    "of",
    "with",
    "and",
    "or",
    "in",
    "on",
    "at",
    "to",
    "for",
    "from",
    "by",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "this",
    "that",
    "these",
    "those",
    "image",
    "photo",
    "picture",
    "showing",
    "describing",
    "expressing",
    "representing",
    "depicting",
    "historical",
}


# ===============================================================
# CLIP model
# Loaded lazily and cached for process lifetime.
# ===============================================================

_clip_model = None


def _get_clip_model():
    global _clip_model

    if (
        _clip_model is None
        and _CLIP_AVAILABLE
        and ENABLE_CLIP_FILTER
    ):
        log.info(
            f"Loading CLIP model "
            f"({CLIP_MODEL_NAME}) — first call only…"
        )

        t0 = time.time()

        _clip_model = SentenceTransformer(
            CLIP_MODEL_NAME
        )

        log.ok(
            f"CLIP loaded in {time.time() - t0:.1f}s"
        )

    return _clip_model


# ===============================================================
# Main entry point
# ===============================================================

def find_assets(scene: Scene) -> list[str]:
    """
    Find candidate visual assets for a scene.

    Priority:

        1. Local vector B-roll
        2. Pinterest
        3. Wikimedia

    Vector assets are existing reusable videos and are returned
    directly.

    Pinterest/Wikimedia assets are downloaded into the scene's
    asset directory.
    """

    scene_dir = (
        SCENE_ASSETS_DIR
        / f"scene_{scene.id:03d}"
    )

    scene_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # -----------------------------------------------------------
    # Clean previous downloaded candidates.
    #
    # IMPORTANT:
    # Vector videos are NOT stored here, so they are untouched.
    # -----------------------------------------------------------

    for old in scene_dir.glob("candidate_*"):
        old.unlink(missing_ok=True)

    # -----------------------------------------------------------
    # Build search attempts.
    # -----------------------------------------------------------

    attempts = _build_query_attempts(scene)

    if not attempts:
        log.warn(
            f"Scene {scene.id}: no queries available"
        )
        return []

    # CLIP anchor for image sources.
    anchor = (
        scene.english_query
        or scene.arabic_query
        or attempts[0][1]
    )

    # ===========================================================
    # 1. LOCAL VECTOR B-ROLL
    # ===========================================================

    vector_candidates = _vector_candidates(
        scene,
        attempts,
    )

    if vector_candidates:

        log.ok(
            f"Scene {scene.id}: "
            f"vector source found "
            f"{len(vector_candidates)} B-roll candidate(s)"
        )

        return vector_candidates

    log.info(
        f"Scene {scene.id}: "
        f"no suitable vector B-roll found"
    )

    # ===========================================================
    # 2. PINTEREST
    # ===========================================================

    if _PW_AVAILABLE:

        log.info(
            f"Scene {scene.id}: "
            f"trying Pinterest..."
        )

        raw = _pinterest_search(
            scene,
            scene_dir,
            attempts,
        )

        ranked = _post_process(
            raw,
            anchor,
            scene_dir,
            source="pinterest",
        )

        if ranked:
            return ranked

        log.info(
            f"Scene {scene.id}: "
            f"Pinterest produced no relevant hits — "
            f"falling back to Wikimedia"
        )

    else:

        log.info(
            f"Scene {scene.id}: "
            f"Pinterest unavailable — "
            f"using Wikimedia"
        )

    # ===========================================================
    # 3. WIKIMEDIA
    # ===========================================================

    raw = _wikimedia_via_attempts(
        scene,
        scene_dir,
        attempts,
    )

    ranked = _post_process(
        raw,
        anchor,
        scene_dir,
        source="wikimedia",
    )

    if ranked:
        return ranked

    log.warn(
        f"Scene {scene.id}: "
        f"0 candidates total"
    )

    return []


# ===============================================================
# Local Vector B-roll
# ===============================================================

def _vector_candidates(
    scene: Scene,
    attempts: list[tuple[str, str]],
) -> list[str]:
    """
    Search the local semantic B-roll catalog.

    Returns all relevant candidates from the vector source.

    Arabic is preferred because the catalog captions are Arabic.
    English is used as a fallback when Arabic produces nothing.
    """

    # -----------------------------------------------------------
    # Build vector query order.
    #
    # We deliberately use the scene's raw query rather than the
    # shortened Pinterest-style queries.
    # -----------------------------------------------------------

    queries: list[tuple[str, str]] = []

    if scene.arabic_query:
        queries.append(
            ("ar", scene.arabic_query.strip())
        )

    if scene.english_query:
        queries.append(
            ("en", scene.english_query.strip())
        )

    # Remove duplicates.
    seen: set[str] = set()
    unique_queries: list[tuple[str, str]] = []

    for label, query in queries:

        key = query.lower()

        if not key or key in seen:
            continue

        seen.add(key)

        unique_queries.append(
            (label, query)
        )

    # If scene fields are somehow empty, use the first
    # generated query as a final fallback.
    if not unique_queries and attempts:

        unique_queries.append(
            attempts[0]
        )

    # -----------------------------------------------------------
    # Search queries in priority order.
    #
    # We return the first query that produces good matches.
    #
    # This prevents Arabic + English results from creating
    # duplicates while still allowing English fallback.
    # -----------------------------------------------------------

    for label, query in unique_queries:

        log.info(
            f"Scene {scene.id} "
            f"[vector:{label}]: '{query}'"
        )

        try:

            results = search_vector(query)

        except Exception as e:

            log.warn(
                f"Scene {scene.id}: "
                f"vector search failed: {e}"
            )

            continue

        # -------------------------------------------------------
        # Normalize and validate returned paths.
        # -------------------------------------------------------

        valid: list[str] = []
        seen_paths: set[str] = set()

        for path in results:

            if not path:
                continue

            asset = Path(path)

            if not asset.exists():
                log.warn(
                    f"Scene {scene.id}: "
                    f"vector asset missing: {asset}"
                )
                continue

            if asset.suffix.lower() not in _VIDEO_EXTS:
                log.warn(
                    f"Scene {scene.id}: "
                    f"vector source returned non-video "
                    f"asset: {asset}"
                )
                continue

            resolved = str(
                asset.resolve()
            )

            if resolved in seen_paths:
                continue

            seen_paths.add(resolved)
            valid.append(resolved)

        if valid:

            for index, path in enumerate(
                valid,
                start=1,
            ):
                log.info(
                    f"  [vector] candidate "
                    f"{index}: {Path(path).name}"
                )

            return valid

    return []


# ===============================================================
# Post-processing
# phash dedup → CLIP ranking → prune disk
# ===============================================================

def _post_process(
    raw: list[str],
    anchor: str,
    scene_dir: Path,
    source: str,
) -> list[str]:

    if not raw:
        return []

    raw = _phash_dedupe(raw)

    if not raw:
        return []

    ranked = _clip_rank(
        raw,
        anchor,
    )

    # -----------------------------------------------------------
    # Delete rejected downloaded files.
    #
    # Only image-source files are passed here.
    # Vector videos never reach this function.
    # -----------------------------------------------------------

    keep = set(ranked)

    for path in raw:

        if path in keep:
            continue

        try:
            Path(path).unlink(
                missing_ok=True
            )
        except Exception:
            pass

    if ranked:

        log.ok(
            f"[{source}] kept "
            f"{len(ranked)}/{len(raw)} "
            f"relevant image(s)"
        )

    return ranked


# ===============================================================
# Perceptual hash deduplication
# ===============================================================

def _phash_dedupe(
    paths: list[str],
) -> list[str]:

    if not (
        ENABLE_PHASH_DEDUP
        and _PHASH_AVAILABLE
        and _PIL_AVAILABLE
    ):
        return paths

    kept: list[str] = []
    hashes = []

    for path in paths:

        try:

            with Image.open(path) as img:
                h = imagehash.phash(img)

        except Exception:

            continue

        if any(
            h - existing
            <= PHASH_HAMMING_THRESHOLD
            for existing in hashes
        ):
            continue

        hashes.append(h)
        kept.append(path)

    removed = (
        len(paths)
        - len(kept)
    )

    if removed:

        log.info(
            f"  [phash] removed "
            f"{removed} near-duplicate(s)"
        )

    return kept


# ===============================================================
# CLIP ranking
# ===============================================================

def _clip_rank(
    paths: list[str],
    query: str,
) -> list[str]:

    if not paths:
        return []

    # -----------------------------------------------------------
    # No CLIP → file-size ordering fallback.
    # -----------------------------------------------------------

    if not (
        ENABLE_CLIP_FILTER
        and _CLIP_AVAILABLE
        and _PIL_AVAILABLE
    ):

        return sorted(
            paths,
            key=lambda p: Path(p).stat().st_size,
            reverse=True,
        )[:CLIP_TOP_K]

    try:

        model = _get_clip_model()

        if model is None:

            return paths[:CLIP_TOP_K]

        imgs = []
        valid = []

        for path in paths:

            try:

                img = Image.open(path).convert(
                    "RGB"
                )

                imgs.append(img)
                valid.append(path)

            except Exception:
                continue

        if not imgs:
            return []

        text_emb = model.encode(
            [query],
            normalize_embeddings=True,
        )

        img_emb = model.encode(
            imgs,
            normalize_embeddings=True,
            batch_size=8,
        )

        sims = (
            img_emb @ text_emb.T
        ).squeeze(-1).tolist()

        scored = sorted(
            zip(valid, sims),
            key=lambda x: -x[1],
        )

        kept = [
            (path, score)
            for path, score in scored
            if score >= CLIP_MIN_SIMILARITY
        ][:CLIP_TOP_K]

        best = (
            scored[0][1]
            if scored
            else 0.0
        )

        log.info(
            f"  [clip] {len(paths)} → "
            f"{len(kept)} kept "
            f"(best={best:.3f}, "
            f"floor={CLIP_MIN_SIMILARITY})"
        )

        return [
            path
            for path, _score in kept
        ]

    except Exception as e:

        log.warn(
            f"  CLIP failed ({e}); "
            f"using size ordering"
        )

        return sorted(
            paths,
            key=lambda p: Path(p).stat().st_size,
            reverse=True,
        )[:CLIP_TOP_K]


# ===============================================================
# Pinterest
# ===============================================================

def _pinterest_search(
    scene: Scene,
    out_dir: Path,
    attempts: list[tuple[str, str]],
) -> list[str]:
    """Try Pinterest queries in priority order."""

    queries = _prioritize_queries(
        attempts
    )

    if not queries:
        return []

    tmp = (
        WORKSPACE_DIR
        / f"pinterest_scene_{scene.id:03d}"
    )

    if tmp.exists():
        shutil.rmtree(
            tmp,
            ignore_errors=True,
        )

    tmp.mkdir(
        parents=True,
        exist_ok=True,
    )

    for label, query in queries[:3]:

        log.info(
            f"Scene {scene.id} "
            f"[pinterest:{label}]: "
            f"'{query}'"
        )

        try:

            urls = asyncio.run(
                _pinterest_collect_urls(
                    query
                )
            )

        except Exception as e:

            log.warn(
                f"  pinterest browser failed: {e}"
            )

            continue

        if not urls:

            log.info(
                "  pinterest: no URLs scraped"
            )

            continue

        results = _download_parallel(
            urls,
            out_dir,
            max_workers=6,
        )

        if results:

            log.ok(
                f"Scene {scene.id} "
                f"[pinterest:{label}]: "
                f"{len(results)} raw download(s)"
            )

            shutil.rmtree(
                tmp,
                ignore_errors=True,
            )

            return results

    shutil.rmtree(
        tmp,
        ignore_errors=True,
    )

    return []


async def _pinterest_collect_urls(
    query: str,
) -> list[str]:

    async with async_playwright() as pw:

        browser = await pw.chromium.launch(
            headless=PINTEREST_HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )

        ctx_kwargs = dict(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={
                "width": 1440,
                "height": 900,
            },
            locale="en-US",
        )

        cookies_path = Path(
            PINTEREST_COOKIES_FILE
        )

        if cookies_path.exists():

            ctx_kwargs["storage_state"] = str(
                cookies_path
            )

            log.debug(
                "  using cookies.json"
            )

        else:

            log.warn(
                "  cookies.json not found — "
                "results will be worse"
            )

        ctx = await browser.new_context(
            **ctx_kwargs
        )

        page = await ctx.new_page()

        url = (
            "https://www.pinterest.com/search/pins/"
            f"?q={quote_plus(query)}&rs=typed"
        )

        log.info(
            f"  → {url}"
        )

        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=45000,
        )

        await page.wait_for_timeout(
            2500
        )

        seen: set[str] = set()

        for _ in range(
            PINTEREST_SCROLL_ROUNDS
        ):

            srcs = await page.eval_on_selector_all(
                "img",
                "els => els.map("
                "e => e.currentSrc || e.src"
                ").filter(Boolean)",
            )

            for u in srcs:
                seen.add(
                    _upgrade_pinimg(u)
                )

            if len(seen) >= (
                PINTEREST_NUM_IMAGES * 2
            ):
                break

            await page.mouse.wheel(
                0,
                random.randint(
                    1800,
                    3200,
                ),
            )

            await page.wait_for_timeout(
                random.randint(
                    1200,
                    2200,
                )
            )

        await browser.close()

    out = [
        u
        for u in seen
        if (
            "pinimg.com" in u
            and any(
                ext in u.lower()
                for ext in (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                )
            )
        )
    ]

    return out[
        :PINTEREST_NUM_IMAGES * 2
    ]


def _upgrade_pinimg(
    url: str,
) -> str:

    if "pinimg.com" not in url:
        return url

    return re.sub(
        r"/(?:236x|474x|564x|736x)/",
        "/originals/",
        url,
    )


# ===============================================================
# Parallel image downloader
# ===============================================================

def _download_parallel(
    urls: list[str],
    out_dir: Path,
    max_workers: int = 6,
) -> list[str]:

    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.pinterest.com/",
    }

    def _one(u: str):

        try:

            r = requests.get(
                u,
                headers=headers,
                timeout=20,
            )

            if (
                r.status_code != 200
                or len(r.content) < 8000
            ):
                return None

            if not _PIL_AVAILABLE:
                return r.content, ".jpg"

            img = Image.open(
                BytesIO(r.content)
            )

            w, h = img.size

            if (
                w < PINTEREST_MIN_RESOLUTION[0]
                or h < PINTEREST_MIN_RESOLUTION[1]
            ):
                return None

            ct = (
                r.headers
                .get("Content-Type", "")
                .lower()
            )

            ext = (
                ".png"
                if "png" in ct
                else ".webp"
                if "webp" in ct
                else ".jpg"
            )

            return r.content, ext

        except Exception:
            return None

    results: list[str] = []
    seen_hashes: set[str] = set()

    with ThreadPoolExecutor(
        max_workers=max_workers
    ) as ex:

        futures = {
            ex.submit(_one, u): u
            for u in urls
        }

        for future in as_completed(
            futures
        ):

            data = future.result()

            if not data:
                continue

            content, ext = data

            content_hash = hashlib.sha1(
                content
            ).hexdigest()

            if content_hash in seen_hashes:
                continue

            seen_hashes.add(
                content_hash
            )

            dest = (
                out_dir
                / f"candidate_{len(results) + 1}{ext}"
            )

            try:

                dest.write_bytes(
                    content
                )

                results.append(
                    str(dest)
                )

                log.info(
                    f"  ↓ {dest.name} "
                    f"({len(content) // 1024} KB)"
                )

            except Exception:
                continue

    return results


# ===============================================================
# Wikimedia
# ===============================================================

def _wikimedia_via_attempts(
    scene: Scene,
    out_dir: Path,
    attempts: list[tuple[str, str]],
) -> list[str]:

    for label, query in attempts:

        log.info(
            f"Scene {scene.id} "
            f"[wiki:{label}]: "
            f"'{query}'"
        )

        results = _wikimedia_search(
            query,
            out_dir,
            count=WIKIMEDIA_RESULT_COUNT,
        )

        if results:

            log.ok(
                f"Scene {scene.id} "
                f"[wiki:{label}]: "
                f"{len(results)} raw download(s)"
            )

            return results

    return []


def _wikimedia_search(
    query: str,
    out_dir: Path,
    count: int = 6,
) -> list[str]:

    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": "6",
        "gsrlimit": count * 4,
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": "1600",
        "format": "json",
        "formatversion": "2",
    }

    data = _http_get_json(
        WIKIMEDIA_API,
        params,
        _HEADERS,
    )

    if not data:
        return []

    pages = (
        data
        .get("query", {})
        .get("pages", [])
    )

    if not pages:
        return []

    candidates: list[
        tuple[str, str]
    ] = []

    for page in pages:

        if len(candidates) >= count * 2:
            break

        info = (
            page.get("imageinfo")
            or [{}]
        )[0]

        mime = info.get(
            "mime",
            "",
        )

        if (
            not mime.startswith("image/")
            or mime == "image/svg+xml"
        ):
            continue

        if (
            info.get("width", 0)
            < WIKIMEDIA_MIN_WIDTH
        ):
            continue

        if (
            info.get("height", 0)
            < WIKIMEDIA_MIN_HEIGHT
        ):
            continue

        url = (
            info.get("thumburl")
            or info.get("url")
        )

        if not url:
            continue

        ext = ".jpg"

        if "png" in mime:
            ext = ".png"

        elif "webp" in mime:
            ext = ".webp"

        candidates.append(
            (url, ext)
        )

    if not candidates:
        return []

    def _one(item):

        url, ext = item

        try:

            r = requests.get(
                url,
                headers=_HEADERS,
                timeout=30,
            )

            if (
                r.status_code == 200
                and len(r.content) > 8000
            ):
                return r.content, ext

        except Exception:
            return None

        return None

    results: list[str] = []

    with ThreadPoolExecutor(
        max_workers=4
    ) as ex:

        futures = [
            ex.submit(_one, candidate)
            for candidate in candidates
        ]

        for future in as_completed(
            futures
        ):

            if len(results) >= count:
                break

            data = future.result()

            if not data:
                continue

            content, ext = data

            dest = (
                out_dir
                / f"candidate_{len(results) + 1}{ext}"
            )

            try:

                dest.write_bytes(
                    content
                )

                results.append(
                    str(dest)
                )

                log.info(
                    f"  ↓ {dest.name} "
                    f"({len(content) // 1024} KB)"
                )

            except Exception:
                continue

    return results


# ===============================================================
# HTTP helper
# ===============================================================

def _http_get_json(
    url: str,
    params: dict,
    headers: dict,
) -> dict | None:

    for attempt in range(
        1,
        _MAX_RETRIES + 1,
    ):

        try:

            r = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=30,
            )

        except requests.RequestException as e:

            log.warn(
                f"  Request error "
                f"(attempt {attempt}): {e}"
            )

            time.sleep(
                2 * attempt
            )

            continue

        if r.status_code == 429:

            wait = int(
                r.headers.get(
                    "Retry-After",
                    2 ** attempt,
                )
            )

            log.warn(
                f"  429 — waiting {wait}s"
            )

            time.sleep(wait)

            continue

        if r.status_code != 200:

            log.warn(
                f"  HTTP {r.status_code} "
                f"(attempt {attempt})"
            )

            time.sleep(
                2 * attempt
            )

            continue

        if not r.text.strip().startswith("{"):

            log.warn(
                f"  Non-JSON response: "
                f"{r.text[:80]!r}"
            )

            return None

        try:

            data = r.json()

        except ValueError as e:

            log.warn(
                f"  JSON parse failed: {e}"
            )

            return None

        time.sleep(
            _MIN_DELAY_WIKI
        )

        return data

    return None


# ===============================================================
# Query building
# ===============================================================

def _build_query_attempts(
    scene: Scene,
) -> list[tuple[str, str]]:

    attempts: list[
        tuple[str, str]
    ] = []

    seen: set[str] = set()

    def add(
        label: str,
        query: str,
    ):

        q = query.strip()

        if not q:
            return

        key = q.lower()

        if key in seen:
            return

        seen.add(key)

        attempts.append(
            (label, q)
        )

    primary: list[
        tuple[str, str]
    ] = []

    if SEARCH_QUERY_PREFERENCE == "arabic":

        if scene.arabic_query:
            primary.append(
                ("ar", scene.arabic_query)
            )

        if (
            SEARCH_FALLBACK_TO_ENGLISH
            and scene.english_query
        ):
            primary.append(
                ("en", scene.english_query)
            )

    elif SEARCH_QUERY_PREFERENCE == "english":

        if scene.english_query:
            primary.append(
                ("en", scene.english_query)
            )

        if (
            SEARCH_FALLBACK_TO_ENGLISH
            and scene.arabic_query
        ):
            primary.append(
                ("ar", scene.arabic_query)
            )

    else:

        if scene.arabic_query:
            primary.append(
                ("ar", scene.arabic_query)
            )

        if scene.english_query:
            primary.append(
                ("en", scene.english_query)
            )

    for label, raw_query in primary:

        add(
            f"{label}:raw",
            raw_query,
        )

        simplified = _simplify_query(
            raw_query
        )

        if (
            simplified
            and simplified.lower()
            != raw_query.lower()
        ):
            add(
                f"{label}:simplified",
                simplified,
            )

        if simplified:

            words = simplified.split()

            if len(words) > 2:

                add(
                    f"{label}:short",
                    " ".join(words[:2]),
                )

    return attempts


def _prioritize_queries(
    attempts: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Prefer raw → simplified → short."""

    ordered: list[
        tuple[str, str]
    ] = []

    seen: set[str] = set()

    for tier in (
        ":raw",
        ":simplified",
        ":short",
    ):

        for label, query in attempts:

            if tier not in label:
                continue

            key = query.strip().lower()

            if key and key not in seen:

                seen.add(key)

                ordered.append(
                    (label, query)
                )

    return ordered[:4]


def _simplify_query(
    query: str,
) -> str:

    cleaned = re.sub(
        r"[^\w\s\u0600-\u06FF]",
        " ",
        query,
    )

    tokens = cleaned.split()

    meaningful = [
        token
        for token in tokens
        if (
            token.lower()
            not in STOP_WORDS
            and len(token) > 1
        )
    ]

    return " ".join(
        meaningful[:5]
    )