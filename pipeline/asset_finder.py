"""Step 3 — Search and download candidate images."""
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import quote_plus

import requests

from config import (
    FBU_BIN, FBU_TIMEOUT, FBU_MAX_CANDIDATES, SCENE_ASSETS_DIR,
    SEARCH_QUERY_PREFERENCE, SEARCH_FALLBACK_TO_ENGLISH,
)
from models.types import Scene
from utils.logger import log


WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = (
    "ArabicVideoEditor/1.0 "
    "(local pipeline; contact: dev@localhost) "
    "python-requests/2.x"
)
MIN_DELAY_BETWEEN_REQUESTS = 1.2
MAX_RETRIES = 3


_FBU_PATH = shutil.which(FBU_BIN)


def find_assets(scene: Scene) -> list[str]:
    scene_dir = SCENE_ASSETS_DIR / f"scene_{scene.id:03d}"
    scene_dir.mkdir(parents=True, exist_ok=True)

    # Build the list of queries to try, in order
    queries: list[tuple[str, str]] = []   # (label, query_text)

    if SEARCH_QUERY_PREFERENCE == "arabic":
        if scene.arabic_query:
            queries.append(("ar", scene.arabic_query))
        if SEARCH_FALLBACK_TO_ENGLISH and scene.english_query:
            queries.append(("en", scene.english_query))
    elif SEARCH_QUERY_PREFERENCE == "english":
        if scene.english_query:
            queries.append(("en", scene.english_query))
        if SEARCH_FALLBACK_TO_ENGLISH and scene.arabic_query:
            queries.append(("ar", scene.arabic_query))
    else:  # "both"
        if scene.arabic_query:
            queries.append(("ar", scene.arabic_query))
        if scene.english_query:
            queries.append(("en", scene.english_query))

    if not queries:
        log.warn(f"Scene {scene.id}: no queries available")
        return []

    downloaded: list[str] = []
    for label, q in queries:
        log.info(f"Scene {scene.id} [{label}]: '{q[:70]}'")
        downloaded = _wikimedia_search(q, scene_dir, count=3)
        if downloaded:
            log.ok(f"Scene {scene.id} [{label}]: {len(downloaded)} hits")
            break
        log.info(f"Scene {scene.id} [{label}]: no results")

    if not downloaded and _FBU_PATH:
        log.info(f"Scene {scene.id}: trying fbu fallback...")
        downloaded = _try_fbu(scene, scene_dir)

    log.info(f"Scene {scene.id}: {len(downloaded)} candidates total")
    return downloaded


def _wikimedia_search(query: str, out_dir: Path, count: int = 3) -> list[str]:
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": "6",       # File namespace
        "gsrlimit": count * 3,
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
            log.warn(f"  429 — waiting {wait}s "
                     f"(attempt {attempt}/{MAX_RETRIES})")
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


def _try_fbu(scene: Scene, out_dir: Path) -> list[str]:
    if not _FBU_PATH:
        return []

    # Prefer Arabic for the browser search too
    q = scene.arabic_query or scene.english_query
    search_url = (
        f"https://commons.wikimedia.org/w/index.php?search="
        f"{quote_plus(q)}"
    )
    goal = (
        f"Find the top {FBU_MAX_CANDIDATES} image thumbnails on this "
        f"search results page."
    )

    cmd = [
        "timeout", "--kill-after=5", str(FBU_TIMEOUT - 10),
        _FBU_PATH, "run", search_url,
        "--goal", goal,
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True,
                       timeout=FBU_TIMEOUT)
    except subprocess.TimeoutExpired:
        log.warn("  fbu timed out")
    except Exception as e:
        log.warn(f"  fbu error: {e}")

    return []