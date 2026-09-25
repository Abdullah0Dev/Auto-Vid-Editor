"""Arabic Historical Video Editor — CLI.

Usage:
    python main.py                              # uses input/recording.mp4
    python main.py path/to/video.mp4            # explicit input
    python main.py video.mp4 --bg-music song.mp3
    python main.py video.mp4 --nasheed anthem.mp3
    python main.py --random-bg                  # auto-pick from assets/bg_music/
"""
import argparse
import random
import sys
from pathlib import Path

from config import DEFAULT_VIDEO, BG_MUSIC_DIR, NASHEED_DIR
from pipeline.orchestrator import run
from utils.logger import log


def pick_random(folder: Path) -> str | None:
    if not folder.exists():
        return None
    files = [p for p in folder.iterdir()
             if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".opus")]
    return str(random.choice(files)) if files else None


def main():
    parser = argparse.ArgumentParser(description="Arabic historical video editor")
    parser.add_argument("video", nargs="?", default=None,
                        help=f"Input MP4 (default: {DEFAULT_VIDEO})")
    parser.add_argument("--bg-music", default=None,
                        help="Background music file")
    parser.add_argument("--nasheed", default=None,
                        help="Nasheed file (اناشيد حماسية)")
    parser.add_argument("--random-bg", action="store_true",
                        help="Auto-pick random bg music from assets/bg_music/")
    parser.add_argument("--random-nasheed", action="store_true",
                        help="Auto-pick random nasheed from assets/nasheed/")
    args = parser.parse_args()

    video = Path(args.video) if args.video else DEFAULT_VIDEO
    if not video.exists():
        log.error(f"Video not found: {video}")
        log.info(f"Drop a file in {DEFAULT_VIDEO.parent}/ or pass a path.")
        sys.exit(1)

    bg = args.bg_music or (pick_random(BG_MUSIC_DIR) if args.random_bg else None)
    nasheed = args.nasheed or (pick_random(NASHEED_DIR) if args.random_nasheed else None)

    if bg: log.info(f"Background music: {Path(bg).name}")
    if nasheed: log.info(f"Nasheed: {Path(nasheed).name}")

    run(str(video), bg_music=bg, nasheed=nasheed)


if __name__ == "__main__":
    main()