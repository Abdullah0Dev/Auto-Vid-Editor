"""Arabic Historical Video Editor — CLI.

Usage:
    python main.py                              # uses .env settings
    python main.py path/to/video.mp4            # explicit input
    python main.py video.mp4 --bg-music song.mp3
    python main.py video.mp4 --nasheed anthem.mp3
    python main.py --random-bg

    # Provider overrides (one-shot, ignore .env)
    python main.py --provider gemini
    python main.py --provider gemini --api-key AIzaSy...
    python main.py --provider ollama
"""
import os
import sys


# ═══════════════════════════════════════════════════════════
#  Read --provider / --api-key BEFORE importing config,
#  so config sees the right env vars when it runs.
# ═══════════════════════════════════════════════════════════
def _apply_early_args():
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--provider" and i + 1 < len(args):
            os.environ["LLM_PROVIDER"] = args[i + 1]
        if a == "--api-key" and i + 1 < len(args):
            os.environ["GEMINI_API_KEY"] = args[i + 1]


_apply_early_args()


# ═══════════════════════════════════════════════════════════
#  Now safe to import everything that reads config
# ═══════════════════════════════════════════════════════════
import argparse
import random
from pathlib import Path

from config import (
    DEFAULT_VIDEO, BG_MUSIC_DIR, NASHEED_DIR,
    LLM_PROVIDER, MODEL_ORCHESTRATOR, MODEL_VISION,
    GEMINI_API_KEY,
)
from pipeline.orchestrator import run
from utils.logger import log, console


def pick_random(folder: Path) -> str | None:
    if not folder.exists():
        return None
    files = [p for p in folder.iterdir()
             if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".opus")]
    return str(random.choice(files)) if files else None


def print_banner():
    console.rule("[bold gold1]Arabic Historical Video Editor")
    console.print(f"  [cyan]Provider:[/cyan]  [bold]{LLM_PROVIDER}[/bold]")
    console.print(f"  [cyan]Model:[/cyan]     {MODEL_ORCHESTRATOR}")
    console.print(f"  [cyan]Vision:[/cyan]    {MODEL_VISION or '[dim](disabled)[/dim]'}")

    if LLM_PROVIDER == "gemini":
        if GEMINI_API_KEY:
            key_preview = GEMINI_API_KEY[:6] + "…" + GEMINI_API_KEY[-4:]
            console.print(f"  [cyan]API key:[/cyan]   {key_preview}")
        else:
            console.print("  [red]API key:[/red]   [bold]NOT SET[/bold] "
                          "— add GEMINI_API_KEY to .env or pass --api-key")

    console.rule()


def main():
    parser = argparse.ArgumentParser(
        description="Arabic historical video editor")
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
    parser.add_argument("--provider", choices=["ollama", "gemini"],
                        default=None,
                        help="LLM provider (overrides .env)")
    parser.add_argument("--api-key", default=None,
                        help="Gemini API key (overrides .env)")
    args = parser.parse_args()

    video = Path(args.video) if args.video else DEFAULT_VIDEO
    if not video.exists():
        log.error(f"Video not found: {video}")
        log.info(f"Drop a file in {DEFAULT_VIDEO.parent}/ or pass a path.")
        sys.exit(1)

    bg = args.bg_music or (pick_random(BG_MUSIC_DIR)
                           if args.random_bg else None)
    nasheed = args.nasheed or (pick_random(NASHEED_DIR)
                               if args.random_nasheed else None)

    print_banner()
    if bg:
        log.info(f"Background music: {Path(bg).name}")
    if nasheed:
        log.info(f"Nasheed: {Path(nasheed).name}")

    run(str(video), bg_music=bg, nasheed=nasheed)


if __name__ == "__main__":
    main()