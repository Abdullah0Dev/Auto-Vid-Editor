"""Step 5 — Search and download candidate images.

Primary source: Pinterest (via pinterest-dl) — huge visual library,
great for historical, Islamic, and Arabic content.

Fallbacks: Wikimedia Commons API, then fast-browser-use (optional).
"""
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
    SEARCH_SOURCE, PINTEREST_NUM_IMAGES, PINTEREST_MIN_RESOLUTION,
)
from models.types import Scene
from utils.logger import log


# --- Optional Pinterest import ---
try:
    from pinterest_dl import PinterestDL
    _PINTEREST_AVAILABLE = True
except ImportError:
    _PINTEREST_AVAILABLE = False
    log.warn("pinterest-dl not installed — run: pip install pinterest-dl")


# --- Wikimedia ---
WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = (
    "ArabicVideoEditor/1.0 "
    "(local pipeline; contact: dev@localhost) "
    "python-requests/2.x"
)
MIN_DELAY_BETWEEN_REQUESTS = 1.0
MAX_RETRIES = 3

_FBU_PATH = shutil.which(FBU_BIN)


# Words we strip from queries — they add nothing for image search
STOP_WORDS = {
    "the", "a", "an", "of", "with", "and", "or", "in", "on", "at", "to",
    "for", "from", "by", "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those", "image", "photo", "picture", "showing",
    "describing", "expressing", "representing", "depicting",
    "historical",
}


# ===============================================================
# Main entry point
# ===============================================================

def find_assets(scene: Scene) -> list[str]:
    """Find and download candidate images for a scene."""
    scene_dir = SCENE_ASSETS_DIR / f"scene_{scene.id:03d}"
    scene_dir.mkdir(parents=True, exist_ok=True)

    attempts = _build_query_attempts(scene)
    if not attempts:
        log.warn(f"Scene {scene.id}: no queries available")
        return []

    # Route to the configured primary source
    if SEARCH_SOURCE == "pinterest" and _PINTEREST_AVAILABLE:
        downloaded = _search_pinterest(scene, scene_dir, attempts)
        if downloaded:
            return downloaded
        log.info(f"Scene {scene.id}: Pinterest returned nothing, "
                 f"falling back to Wikimedia")

    # Wikimedia fallback (works regardless of SEARCH_SOURCE if Pinterest missed)
    for label, query in attempts:
        log.info(f"Scene {scene.id} [wiki:{label}]: '{query}'")
        downloaded = _wikimedia_search(query, scene_dir, count=3)
        if downloaded:
            log.ok(f"Scene {scene.id} [wiki:{label}]: {len(downloaded)} hits")
            return downloaded

    # Last resort: fbu browser automation (disabled by default)
    from config import ENABLE_FBU_FALLBACK
    if ENABLE_FBU_FALLBACK and _FBU_PATH:
        log.info(f"Scene {scene.id}: trying fbu fallback...")
        downloaded = _try_fbu_download(scene, scene_dir)
        if downloaded:
            return downloaded

    log.info(f"Scene {scene.id}: 0 candidates total")
    return []


# ===============================================================
# Pinterest (primary source)
# ===============================================================

def _search_pinterest(scene: Scene, out_dir: Path,
                      attempts: list[tuple[str, str]]) -> list[str]:
    """
    Search Pinterest using pinterest-dl and download top images.

    Uses API-mode (no browser needed, faster, no login required
    for public content). Downloads to a temp dir, then renames
    files to candidate_N.jpg for consistent downstream handling.
    """
    if not _PINTEREST_AVAILABLE:
        return []

    # Use the first (best) attempt query
    _, query = attempts[0]
    log.info(f"Scene {scene.id} [pinterest]: '{query}'")

    tmp_dir = WORKSPACE_DIR / f"pinterest_scene_{scene.id:03d}"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        downloaded = PinterestDL.with_api().search_and_download(
            query=query,
            output_dir=str(tmp_dir),
            num=PINTEREST_NUM_IMAGES,
            min_resolution=PINTEREST_MIN_RESOLUTION,
        )
    except Exception as e:
        log.warn(f"  Pinterest search failed: {e}")
        # Try a simplified query as a second chance
        simplified = _simplify_query(query)
        if simplified and simplified.lower() != query.lower():
            log.info(f"  Retrying Pinterest with: '{simplified}'")
            try:
                downloaded = PinterestDL.with_api().search_and_download(
                    query=simplified,
                    output_dir=str(tmp_dir),
                    num=PINTEREST_NUM_IMAGES,
                    min_resolution=PINTEREST_MIN_RESOLUTION,
                )
            except Exception as e2:
                log.warn(f"  Pinterest retry failed: {e2}")
                return []
        else:
            return []

    if not downloaded:
        log.info(f"  Pinterest: no results")
        return []

    # Normalize filenames to candidate_N.jpg
    results = _normalize_pinterest_files(tmp_dir, out_dir)
    if results:
        log.ok(f"Scene {scene.id} [pinterest]: {len(results)} hits")
    else:
        log.info(f"Scene {scene.id} [pinterest]: 0 usable images")
    return results


def _normalize_pinterest_files(src_dir: Path, dest_dir: Path) -> list[str]:
    """
    Rename pinterest-dl output files to candidate_1.jpg, candidate_2.jpg, ...
    pinterest-dl saves files like '{pin_id}.jpg' or '{pin_id}.png'.
    """
    # Find all image files in the temp dir
    images = sorted([
        p for p in src_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
    ])

    results: list[str] = []
    for i, src in enumerate(images[:FBU_MAX_CANDIDATES], start=1):
        ext = ".jpg"
        if src.suffix.lower() == ".png":
            ext = ".png"
        elif src.suffix.lower() == ".webp":
            ext = ".webp"
        elif src.suffix.lower() == ".jpeg":
            ext = ".jpg"

        # Validate size — reject tiny files (icons, blanks)
        if src.stat().st_size < 5000:
            log.debug(f"  Skipping tiny file: {src.name}")
            continue

        dest = dest_dir / f"candidate_{len(results) + 1}{ext}"
        shutil.copy2(src, dest)
        results.append(str(dest))
        log.info(f"  ↓ {dest.name} ({src.stat().st_size // 1024} KB)")

    # Clean up temp dir
    try:
        shutil.rmtree(src_dir)
    except Exception:
        pass

    return results


# ===============================================================
# Query strategy (shared by Pinterest + Wikimedia)
# ===============================================================

def _build_query_attempts(scene: Scene) -> list[tuple[str, str]]:
    """Build a prioritized list of (label, query) attempts."""
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


def _simplify_query(query: str) -> str:
    """Strip stop words and keep 2-4 meaningful keywords."""
    cleaned = re.sub(r"[^\w\s\u0600-\u06FF]", " ", query)
    tokens = cleaned.split()
    meaningful = [
        t for t in tokens
        if t.lower() not in STOP_WORDS and len(t) > 1
    ]
    return " ".join(meaningful[:4])


# ===============================================================
# Wikimedia fallback
# ===============================================================

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


# ===============================================================
# fbu fallback (browser automation — disabled by default)
# ===============================================================

def _try_fbu_download(scene: Scene, out_dir: Path) -> list[str]:
    if not _FBU_PATH:
        return []

    q = scene.english_query or scene.arabic_query
    q = _simplify_query(q) or q

    # Search Pinterest via fbu as last resort
    search_url = f"https://www.pinterest.com/search/pins/?q={quote_plus(q)}"
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