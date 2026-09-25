"""Step 5 — Search and download candidate images."""
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import quote_plus

import requests

from config import (
    FBU_BIN, FBU_TIMEOUT, FBU_MAX_CANDIDATES, SCENE_ASSETS_DIR,
    SEARCH_QUERY_PREFERENCE, SEARCH_FALLBACK_TO_ENGLISH, WORKSPACE_DIR,
)
from models.types import Scene
from utils.logger import log


WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = (
    "ArabicVideoEditor/1.0 "
    "(local pipeline; contact: dev@localhost) "
    "python-requests/2.x"
)
MIN_DELAY_BETWEEN_REQUESTS = 1.0
MAX_RETRIES = 3

_FBU_PATH = shutil.which(FBU_BIN)


# Words we strip from queries — they add nothing for Wikimedia search
STOP_WORDS = {
    "the", "a", "an", "of", "with", "and", "or", "in", "on", "at", "to",
    "for", "from", "by", "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those", "image", "photo", "picture", "showing",
    "describing", "expressing", "representing", "depicting",
    "historical",   # too generic — we add it back only as a fallback
}


def find_assets(scene: Scene) -> list[str]:
    """Main entry point: find and download candidate images for a scene."""
    scene_dir = SCENE_ASSETS_DIR / f"scene_{scene.id:03d}"
    scene_dir.mkdir(parents=True, exist_ok=True)

    # Build ordered list of query attempts
    attempts = _build_query_attempts(scene)

    if not attempts:
        log.warn(f"Scene {scene.id}: no queries available")
        return []

    downloaded: list[str] = []

    for label, query in attempts:
        log.info(f"Scene {scene.id} [{label}]: '{query}'")

        downloaded = _wikimedia_search(query, scene_dir, count=3)
        if downloaded:
            log.ok(f"Scene {scene.id} [{label}]: {len(downloaded)} hits")
            return downloaded

        log.info(f"Scene {scene.id} [{label}]: no results")

    # Last resort: fbu browser navigation (only if enabled)
    from config import ENABLE_FBU_FALLBACK
    if not downloaded and ENABLE_FBU_FALLBACK and _FBU_PATH:
        log.info(f"Scene {scene.id}: trying fbu fallback...")
        downloaded = _try_fbu_download(scene, scene_dir)

    log.info(f"Scene {scene.id}: {len(downloaded)} candidates total")
    return downloaded


# ---------------------------------------------------------------
# Query strategy
# ---------------------------------------------------------------

def _build_query_attempts(scene: Scene) -> list[tuple[str, str]]:
    """
    Build a prioritized list of (label, query) attempts.

    Wikimedia search is AND-based, so long queries return 0. We:
      1. Simplify the LLM query (strip stop words, keep 2-4 keywords)
      2. Fall back to even shorter versions if needed
      3. Try both English and Arabic in the configured order
    """
    attempts: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(label: str, query: str):
        q = query.strip()
        if not q or q.lower() in seen:
            return
        seen.add(q.lower())
        attempts.append((label, q))

    # Build the primary query list based on config
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
        # 1. Raw query as-is (may work if it happens to be short)
        add(f"{label}:raw", raw_query)

        # 2. Simplified: strip stop words, keep 2-4 meaningful keywords
        simplified = _simplify_query(raw_query)
        if simplified and simplified.lower() != raw_query.lower():
            add(f"{label}:simplified", simplified)

        # 3. Ultra-short: first 2 keywords of the simplified query
        if simplified:
            words = simplified.split()
            if len(words) > 2:
                add(f"{label}:short", " ".join(words[:2]))

    return attempts


def _simplify_query(query: str) -> str:
    """
    Strip stop words and filler words from a query, keep the most
    meaningful 2-4 tokens.

    Examples:
      "old Arabic manuscript expressing loss"
        → "old Arabic manuscript"
      "white manuscript page with Arabic calligraphy describing Imam Muhammad"
        → "manuscript Arabic calligraphy"
      "Image of historian with historical reference"
        → "historian reference"
    """
    # Remove punctuation
    cleaned = re.sub(r"[^\w\s\u0600-\u06FF]", " ", query)
    tokens = cleaned.split()

    # Filter out stop words (case-insensitive)
    meaningful = [
        t for t in tokens
        if t.lower() not in STOP_WORDS and len(t) > 1
    ]

    # Keep at most 4 tokens — longer and Wikimedia rarely matches
    return " ".join(meaningful[:4])


# ---------------------------------------------------------------
# Wikimedia search
# ---------------------------------------------------------------

def _wikimedia_search(query: str, out_dir: Path, count: int = 3) -> list[str]:
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": "6",
        "gsrlimit": count * 4,
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": "1280",
        "format": "json",
        "formatversion": "2",
    }
    headers = {"User-Agent": USER_AGENT}

    data = _http_get_json(WIKIMEDIA_API, params, headers)
    if data is None:
        return []

    pages = data.get("query", {}).get("pages", [])
    if not pages:
        return []

    results = []
    for page in pages:
        if len(results) >= count:
            break
        infos = page.get("imageinfo", [])
        if not infos:
            continue
        info = infos[0]

        mime = info.get("mime", "")
        if not mime.startswith("image/") or mime == "image/svg+xml":
            continue
        if info.get("width", 0) < 600 or info.get("height", 0) < 400:
            continue

        url = info.get("thumburl") or info.get("url")
        if not url:
            continue

        ext = ".jpg"
        if "png" in mime:
            ext = ".png"
        elif "webp" in mime:
            ext = ".webp"

        out = out_dir / f"candidate_{len(results) + 1}{ext}"
        try:
            img = requests.get(url, headers=headers, timeout=30)
            if img.status_code == 200 and len(img.content) > 5000:
                out.write_bytes(img.content)
                results.append(str(out))
                log.info(f"  ↓ {out.name} ({len(img.content) // 1024} KB)")
        except requests.RequestException as e:
            log.warn(f"  Download failed: {e}")
            continue

    return results


def _http_get_json(url: str, params: dict, headers: dict) -> dict | None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=30)
        except requests.RequestException as e:
            log.warn(f"  Request error (attempt {attempt}): {e}")
            time.sleep(2 * attempt)
            continue

        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 2 ** attempt))
            log.warn(f"  429 — waiting {wait}s (attempt {attempt}/{MAX_RETRIES})")
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

        time.sleep(MIN_DELAY_BETWEEN_REQUESTS)
        return data

    return None


# ---------------------------------------------------------------
# fbu fallback (browser automation)
# ---------------------------------------------------------------

def _try_fbu_download(scene: Scene, out_dir: Path) -> list[str]:
    if not _FBU_PATH:
        return []

    q = scene.english_query or scene.arabic_query
    q = _simplify_query(q) or q   # use the short version for the browser too

    search_url = (
        f"https://commons.wikimedia.org/w/index.php?search={quote_plus(q)}"
    )
    goal = (
        f"Find the top {FBU_MAX_CANDIDATES} image thumbnails on this "
        f"search results page. Report the direct image URLs."
    )

    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    trace_file = WORKSPACE_DIR / f"fbu_scene_{scene.id:03d}.json"

    cmd = [
        _FBU_PATH, "run", search_url,
        "--goal", goal,
        "--trace", str(trace_file),
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=FBU_TIMEOUT,
        )
        log.info(f"  fbu exit code: {result.returncode}")
    except subprocess.TimeoutExpired:
        log.warn("  fbu timed out")
        return []
    except Exception as e:
        log.warn(f"  fbu error: {e}")
        return []

    urls = _extract_urls_from_trace(trace_file)
    if not urls:
        return []

    log.info(f"  fbu found {len(urls)} candidate URL(s)")
    return _download_from_urls(urls, out_dir)


def _extract_urls_from_trace(trace_file: Path) -> list[str]:
    if not trace_file.exists():
        return []
    try:
        import json as _json
        data = _json.loads(trace_file.read_text(encoding="utf-8"))
    except Exception:
        return []

    urls: list[str] = []

    def _walk(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)
        elif isinstance(obj, str):
            if obj.startswith("http") and any(
                ext in obj.lower()
                for ext in (".jpg", ".jpeg", ".png", ".webp", "/thumb/")
            ):
                urls.append(obj)

    _walk(data)
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:6]


def _download_from_urls(urls: list[str], out_dir: Path) -> list[str]:
    headers = {"User-Agent": USER_AGENT}
    results = []
    for url in urls:
        if len(results) >= FBU_MAX_CANDIDATES:
            break
        try:
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code != 200 or len(r.content) < 5000:
                continue
            ctype = r.headers.get("Content-Type", "").lower()
            ext = ".jpg"
            if "png" in ctype:
                ext = ".png"
            elif "webp" in ctype:
                ext = ".webp"
            out = out_dir / f"candidate_{len(results) + 1}{ext}"
            out.write_bytes(r.content)
            results.append(str(out))
            log.info(f"  ↓ {out.name} ({len(r.content) // 1024} KB)")
        except Exception as e:
            log.warn(f"  Download failed: {e}")
            continue
    return results