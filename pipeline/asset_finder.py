"""Step 3 — Search and download candidate images."""
import subprocess, requests
from pathlib import Path
from config import (FBU_BIN, FBU_TIMEOUT, FBU_MAX_CANDIDATES,
                    SCENE_ASSETS_DIR)
from models.types import Scene
from utils.logger import log


def find_assets(scene: Scene) -> list[str]:
    scene_dir = SCENE_ASSETS_DIR / f"scene_{scene.id:03d}"
    scene_dir.mkdir(parents=True, exist_ok=True)

    downloaded = _try_fbu(scene, scene_dir)
    if not downloaded:
        log.warn(f"fast-browser-use failed, falling back to Wikimedia API")
        downloaded = _wikimedia_search(scene.english_query, scene_dir)

    log.info(f"Scene {scene.id}: {len(downloaded)} candidates")
    return downloaded


def _try_fbu(scene: Scene, out_dir: Path) -> list[str]:
    """Attempt to use fast-browser-use CLI."""
    url = f"https://commons.wikimedia.org/w/index.php?search={scene.english_query.replace(' ', '+')}"
    goal = (
        f"Find the top {FBU_MAX_CANDIDATES} historical images and download "
        f"them to {out_dir}/candidate_1.jpg, candidate_2.jpg, candidate_3.jpg"
    )
    try:
        subprocess.run(
            [FBU_BIN, "run", url, "--goal", goal, "--timeout", "120"],
            capture_output=True, text=True, timeout=FBU_TIMEOUT,
        )
    except Exception as e:
        log.warn(f"fbu error: {e}")
        return []

    return _collect_files(out_dir)


def _wikimedia_search(query: str, out_dir: Path, count: int = 3) -> list[str]:
    """Direct API fallback — no browser needed."""
    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php", params={
            "action": "query", "generator": "search",
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrlimit": count * 2, "prop": "imageinfo",
            "iiprop": "url|mime", "iiurlwidth": "1280", "format": "json",
        }, timeout=30)
        pages = r.json().get("query", {}).get("pages", {})
    except Exception as e:
        log.warn(f"Wikimedia search failed: {e}")
        return []

    results = []
    for i, page in enumerate(pages.values()):
        if len(results) >= count:
            break
        info = page.get("imageinfo", [{}])[0]
        url = info.get("thumburl") or info.get("url")
        if not url:
            continue
        ext = ".jpg" if "jpeg" in info.get("mime", "") else ".png"
        out = out_dir / f"candidate_{len(results) + 1}{ext}"
        try:
            img = requests.get(url, timeout=30)
            if img.status_code == 200 and len(img.content) > 5000:
                out.write_bytes(img.content)
                results.append(str(out))
        except Exception:
            continue
    return results


def _collect_files(d: Path) -> list[str]:
    return [str(p) for p in sorted(d.glob("candidate_*"))
            if p.is_file() and p.stat().st_size > 1000]