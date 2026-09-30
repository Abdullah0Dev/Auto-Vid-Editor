"""Step 5 — Search and download candidate images.

Primary : Pinterest (Playwright — the real web UI, not the API)
Fallback: Wikimedia Commons
Filter  : CLIP relevance gate + perceptual-hash dedup
"""
from __future__ import annotations

import asyncio
import hashlib
import random
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote_plus

import requests

from config import (
    SCENE_ASSETS_DIR, WORKSPACE_DIR,
    SEARCH_QUERY_PREFERENCE, SEARCH_FALLBACK_TO_ENGLISH,
    PINTEREST_NUM_IMAGES, PINTEREST_MIN_RESOLUTION,
    PINTEREST_SCROLL_ROUNDS, PINTEREST_COOKIES_FILE, PINTEREST_HEADLESS,
    ENABLE_CLIP_FILTER, CLIP_MODEL_NAME, CLIP_MIN_SIMILARITY, CLIP_TOP_K,
    ENABLE_PHASH_DEDUP, PHASH_HAMMING_THRESHOLD,
    WIKIMEDIA_RESULT_COUNT, WIKIMEDIA_MIN_WIDTH, WIKIMEDIA_MIN_HEIGHT,
)
from models.types import Scene
from utils.logger import log


# ===============================================================
# Optional imports
# ===============================================================
try:
    from playwright.async_api import async_playwright
    _PW_AVAILABLE = True
except ImportError:
    _PW_AVAILABLE = False
    log.warn("playwright not installed — run: pip install playwright && playwright install chromium")

try:
    from PIL import Image
    from io import BytesIO
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

try:
    import torch
    from sentence_transformers import SentenceTransformer
    _CLIP_AVAILABLE = True
except ImportError:
    _CLIP_AVAILABLE = False
    log.warn("CLIP deps missing — run: pip install sentence-transformers torch")

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
    "ArabicVideoEditor/1.0 (local pipeline; contact: dev@localhost) "
    "python-requests/2.x"
)
_HEADERS = {"User-Agent": USER_AGENT}
_MIN_DELAY_WIKI = 1.0
_MAX_RETRIES = 3
_IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

STOP_WORDS = {
    "the","a","an","of","with","and","or","in","on","at","to","for","from","by",
    "is","are","was","were","be","been","being","this","that","these","those",
    "image","photo","picture","showing","describing","expressing","representing",
    "depicting","historical",
}


# ===============================================================
# CLIP model — loaded lazily, cached for the process lifetime
# ===============================================================
_clip_model = None

def _get_clip_model():
    global _clip_model
    if _clip_model is None and _CLIP_AVAILABLE and ENABLE_CLIP_FILTER:
        log.info(f"Loading CLIP model ({CLIP_MODEL_NAME}) — first call only…")
        t0 = time.time()
        _clip_model = SentenceTransformer(CLIP_MODEL_NAME)
        log.ok(f"CLIP loaded in {time.time() - t0:.1f}s")
    return _clip_model


# ===============================================================
# Main entry point
# ===============================================================

def find_assets(scene: Scene) -> list[str]:
    """Find and download candidate images for a scene."""
    scene_dir = SCENE_ASSETS_DIR / f"scene_{scene.id:03d}"
    scene_dir.mkdir(parents=True, exist_ok=True)

    # Clean any leftovers from a previous run
    for old in scene_dir.glob("candidate_*"):
        old.unlink(missing_ok=True)

    attempts = _build_query_attempts(scene)
    if not attempts:
        log.warn(f"Scene {scene.id}: no queries available")
        return []

    # Anchor text for CLIP — prefer English (CLIP's training is English-heavy)
    anchor = scene.english_query or scene.arabic_query or attempts[0][1]

    # ── 1. Pinterest (browser) ────────────────────────────
    if _PW_AVAILABLE:
        raw = _pinterest_search(scene, scene_dir, attempts)
        ranked = _post_process(raw, anchor, scene_dir, source="pinterest")
        if ranked:
            return ranked
        log.info(f"Scene {scene.id}: Pinterest produced no relevant hits, "
                 f"falling back to Wikimedia")

    # ── 2. Wikimedia ──────────────────────────────────────
    raw = _wikimedia_via_attempts(scene, scene_dir, attempts)
    ranked = _post_process(raw, anchor, scene_dir, source="wikimedia")
    if ranked:
        return ranked

    log.info(f"Scene {scene.id}: 0 candidates total")
    return []


# ===============================================================
# Post-processing: phash dedup → CLIP ranking → prune disk
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

    ranked = _clip_rank(raw, anchor)

    # Delete rejected files so downstream only sees the winners
    keep = set(ranked)
    for p in raw:
        if p not in keep:
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass

    if ranked:
        log.ok(f"[{source}] kept {len(ranked)}/{len(raw)} relevant image(s)")
    return ranked


def _phash_dedupe(paths: list[str]) -> list[str]:
    if not (ENABLE_PHASH_DEDUP and _PHASH_AVAILABLE):
        return paths
    kept, hashes = [], []
    for p in paths:
        try:
            h = imagehash.phash(Image.open(p))
        except Exception:
            continue
        if any(h - hh <= PHASH_HAMMING_THRESHOLD for hh in hashes):
            continue
        hashes.append(h)
        kept.append(p)
    if len(kept) != len(paths):
        log.info(f"  [phash] removed {len(paths) - len(kept)} near-duplicate(s)")
    return kept


def _clip_rank(paths: list[str], query: str) -> list[str]:
    if not paths:
        return []
    if not (ENABLE_CLIP_FILTER and _CLIP_AVAILABLE and _PIL_AVAILABLE):
        # No CLIP → fall back to file-size ordering
        return sorted(paths, key=lambda p: Path(p).stat().st_size, reverse=True)[:CLIP_TOP_K]

    try:
        model = _get_clip_model()
        if model is None:
            return paths[:CLIP_TOP_K]

        imgs, valid = [], []
        for p in paths:
            try:
                imgs.append(Image.open(p).convert("RGB"))
                valid.append(p)
            except Exception:
                continue
        if not imgs:
            return []

        text_emb = model.encode([query], normalize_embeddings=True)
        img_emb = model.encode(imgs, normalize_embeddings=True, batch_size=8)
        sims = (img_emb @ text_emb.T).squeeze(-1).tolist()

        scored = sorted(zip(valid, sims), key=lambda x: -x[1])
        kept = [(p, s) for p, s in scored if s >= CLIP_MIN_SIMILARITY][:CLIP_TOP_K]

        best = scored[0][1] if scored else 0.0
        log.info(
            f"  [clip] {len(paths)} → {len(kept)} kept "
            f"(best={best:.3f}, floor={CLIP_MIN_SIMILARITY})"
        )
        return [p for p, _ in kept]
    except Exception as e:
        log.warn(f"  CLIP failed ({e}); using size ordering")
        return sorted(paths, key=lambda p: Path(p).stat().st_size, reverse=True)[:CLIP_TOP_K]


# ===============================================================
# Pinterest (Playwright — real web UI)
# ===============================================================

def _pinterest_search(
    scene: Scene,
    out_dir: Path,
    attempts: list[tuple[str, str]],
) -> list[str]:
    """Try queries in priority order until one yields enough images."""
    queries = _prioritize_queries(attempts)
    if not queries:
        return []

    tmp = WORKSPACE_DIR / f"pinterest_scene_{scene.id:03d}"
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)

    for label, query in queries[:3]:
        log.info(f"Scene {scene.id} [pinterest:{label}]: '{query}'")
        try:
            urls = asyncio.run(_pinterest_collect_urls(query))
        except Exception as e:
            log.warn(f"  pinterest browser failed: {e}")
            continue

        if not urls:
            log.info("  pinterest: no URLs scraped")
            continue

        results = _download_parallel(urls, out_dir, max_workers=6)
        if results:
            log.ok(f"Scene {scene.id} [pinterest:{label}]: {len(results)} raw download(s)")
            shutil.rmtree(tmp, ignore_errors=True)
            return results

    shutil.rmtree(tmp, ignore_errors=True)
    return []


async def _pinterest_collect_urls(query: str) -> list[str]:
    """Launch headless Chromium, search Pinterest, scroll, return image URLs."""
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
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )

        cookies_path = Path(PINTEREST_COOKIES_FILE)
        if cookies_path.exists():
            ctx_kwargs["storage_state"] = str(cookies_path)
            log.debug("  using cookies.json")
        else:
            log.warn("  cookies.json not found — results will be worse")

        ctx = await browser.new_context(**ctx_kwargs)
        page = await ctx.new_page()

        url = (
            "https://www.pinterest.com/search/pins/"
            f"?q={quote_plus(query)}&rs=typed"
        )
        log.info(f"  → {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2500)

        seen: set[str] = set()
        for _ in range(PINTEREST_SCROLL_ROUNDS):
            srcs = await page.eval_on_selector_all(
                "img",
                "els => els.map(e => e.currentSrc || e.src).filter(Boolean)",
            )
            for u in srcs:
                seen.add(_upgrade_pinimg(u))
            if len(seen) >= PINTEREST_NUM_IMAGES * 2:
                break
            await page.mouse.wheel(0, random.randint(1800, 3200))
            await page.wait_for_timeout(random.randint(1200, 2200))

        await browser.close()

    # Filter obvious non-content URLs
    out = [
        u for u in seen
        if "pinimg.com" in u and any(e in u.lower() for e in (".jpg", ".jpeg", ".png", ".webp"))
    ]
    return out[:PINTEREST_NUM_IMAGES * 2]


def _upgrade_pinimg(url: str) -> str:
    """Pinterest thumbnails are /236x/ or /736x/ — try to get the original."""
    if "pinimg.com" not in url:
        return url
    return re.sub(r"/(?:236x|474x|564x|736x)/", "/originals/", url)


def _download_parallel(urls: list[str], out_dir: Path, max_workers: int = 6) -> list[str]:
    """Download in parallel, validate with PIL, return local paths."""
    headers = {"User-Agent": USER_AGENT, "Referer": "https://www.pinterest.com/"}

    def _one(u: str):
        try:
            r = requests.get(u, headers=headers, timeout=20)
            if r.status_code != 200 or len(r.content) < 8000:
                return None
            if not _PIL_AVAILABLE:
                return r.content, ".jpg"
            img = Image.open(BytesIO(r.content))
            w, h = img.size
            if w < PINTEREST_MIN_RESOLUTION[0] or h < PINTEREST_MIN_RESOLUTION[1]:
                return None
            ct = r.headers.get("Content-Type", "").lower()
            ext = ".png" if "png" in ct else ".webp" if "webp" in ct else ".jpg"
            return r.content, ext
        except Exception:
            return None

    results: list[str] = []
    seen_hashes: set[str] = set()

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_one, u): u for u in urls}
        for f in as_completed(futures):
            data = f.result()
            if not data:
                continue
            content, ext = data
            h = hashlib.sha1(content).hexdigest()
            if h in seen_hashes:
                continue
            seen_hashes.add(h)
            dest = out_dir / f"candidate_{len(results) + 1}{ext}"
            try:
                dest.write_bytes(content)
                results.append(str(dest))
                log.info(f"  ↓ {dest.name} ({len(content)//1024} KB)")
            except Exception:
                continue
    return results


# ===============================================================
# Wikimedia (fallback)
# ===============================================================

def _wikimedia_via_attempts(
    scene: Scene,
    out_dir: Path,
    attempts: list[tuple[str, str]],
) -> list[str]:
    for label, query in attempts:
        log.info(f"Scene {scene.id} [wiki:{label}]: '{query}'")
        res = _wikimedia_search(query, out_dir, count=WIKIMEDIA_RESULT_COUNT)
        if res:
            log.ok(f"Scene {scene.id} [wiki:{label}]: {len(res)} raw download(s)")
            return res
    return []


def _wikimedia_search(query: str, out_dir: Path, count: int = 6) -> list[str]:
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
    data = _http_get_json(WIKIMEDIA_API, params, _HEADERS)
    if not data:
        return []

    pages = data.get("query", {}).get("pages", [])
    if not pages:
        return []

    # Collect URLs first, then parallel-download
    candidates: list[tuple[str, str]] = []   # (url, ext)
    for page in pages:
        if len(candidates) >= count * 2:
            break
        info = (page.get("imageinfo") or [{}])[0]
        mime = info.get("mime", "")
        if not mime.startswith("image/") or mime == "image/svg+xml":
            continue
        if info.get("width", 0) < WIKIMEDIA_MIN_WIDTH:
            continue
        if info.get("height", 0) < WIKIMEDIA_MIN_HEIGHT:
            continue
        url = info.get("thumburl") or info.get("url")
        if not url:
            continue
        ext = ".jpg"
        if "png" in mime:
            ext = ".png"
        elif "webp" in mime:
            ext = ".webp"
        candidates.append((url, ext))

    if not candidates:
        return []

    def _one(item):
        url, ext = item
        try:
            r = requests.get(url, headers=_HEADERS, timeout=30)
            if r.status_code == 200 and len(r.content) > 8000:
                return r.content, ext
        except Exception:
            return None
        return None

    results: list[str] = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(_one, c) for c in candidates]
        for f in as_completed(futures):
            if len(results) >= count:
                break
            data = f.result()
            if not data:
                continue
            content, ext = data
            dest = out_dir / f"candidate_{len(results) + 1}{ext}"
            dest.write_bytes(content)
            results.append(str(dest))
            log.info(f"  ↓ {dest.name} ({len(content)//1024} KB)")
    return results


def _http_get_json(url: str, params: dict, headers: dict) -> dict | None:
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=30)
        except requests.RequestException as e:
            log.warn(f"  Request error (attempt {attempt}): {e}")
            time.sleep(2 * attempt)
            continue

        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 2 ** attempt))
            log.warn(f"  429 — waiting {wait}s")
            time.sleep(wait)
            continue
        if r.status_code != 200:
            log.warn(f"  HTTP {r.status_code} (attempt {attempt})")
            time.sleep(2 * attempt)
            continue
        if not r.text.strip().startswith("{"):
            log.warn(f"  Non-JSON response: {r.text[:80]!r}")
            return None
        try:
            data = r.json()
        except ValueError as e:
            log.warn(f"  JSON parse failed: {e}")
            return None
        time.sleep(_MIN_DELAY_WIKI)
        return data
    return None


# ===============================================================
# Query building
# ===============================================================

def _build_query_attempts(scene: Scene) -> list[tuple[str, str]]:
    attempts: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(label: str, query: str):
        q = query.strip()
        if not q or q.lower() in seen:
            return
        seen.add(q.lower())
        attempts.append((label, q))

    primary: list[tuple[str, str]] = []
    if SEARCH_QUERY_PREFERENCE == "arabic":
        if scene.arabic_query:
            primary.append(("ar", scene.arabic_query))
        if SEARCH_FALLBACK_TO_ENGLISH and scene.english_query:
            primary.append(("en", scene.english_query))
    elif SEARCH_QUERY_PREFERENCE == "english":
        if scene.english_query:
            primary.append(("en", scene.english_query))
        if SEARCH_FALLBACK_TO_ENGLISH and scene.arabic_query:
            primary.append(("ar", scene.arabic_query))
    else:
        if scene.arabic_query:
            primary.append(("ar", scene.arabic_query))
        if scene.english_query:
            primary.append(("en", scene.english_query))

    for label, raw_query in primary:
        add(f"{label}:raw", raw_query)
        simplified = _simplify_query(raw_query)
        if simplified and simplified.lower() != raw_query.lower():
            add(f"{label}:simplified", simplified)
        if simplified:
            words = simplified.split()
            if len(words) > 2:
                add(f"{label}:short", " ".join(words[:2]))

    return attempts


def _prioritize_queries(attempts: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Prefer raw → simplified → short, don't repeat the same string."""
    ordered: list[tuple[str, str]] = []
    seen: set[str] = set()
    for tier in (":raw", ":simplified", ":short"):
        for label, query in attempts:
            if tier not in label:
                continue
            key = query.strip().lower()
            if key and key not in seen:
                seen.add(key)
                ordered.append((label, query))
    return ordered[:4]


def _simplify_query(query: str) -> str:
    cleaned = re.sub(r"[^\w\s\u0600-\u06FF]", " ", query)
    tokens = cleaned.split()
    meaningful = [
        t for t in tokens
        if t.lower() not in STOP_WORDS and len(t) > 1
    ]
    return " ".join(meaningful[:5])