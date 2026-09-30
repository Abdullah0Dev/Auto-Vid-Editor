"""All pipeline settings in one place. Edit here, not scattered in code."""

import os
from pathlib import Path
from dotenv import load_dotenv


# ═══════════════════════════════════════════════════════════
#  Paths
# ═══════════════════════════════════════════════════════════
FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

ROOT = Path(__file__).parent
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"
WORKSPACE_DIR = ROOT / "workspace"
MODELS_DIR = ROOT / "models"
WEB_DIR = ROOT / "web"

BG_MUSIC_DIR = ASSETS_DIR / "bg_music"
NASHEED_DIR = ASSETS_DIR / "nasheed"

# Output subfolders
TRANSCRIPT_DIR  = OUTPUT_DIR / "transcript"
PLAN_DIR        = OUTPUT_DIR / "plan"
SCENE_ASSETS_DIR = OUTPUT_DIR / "assets"
CLIPS_DIR       = OUTPUT_DIR / "clips"
FINAL_DIR       = OUTPUT_DIR / "final"

# Default input video (used if none passed via CLI)
DEFAULT_VIDEO = INPUT_DIR / "recording.mp4"


# ═══════════════════════════════════════════════════════════
#  Load .env (from project root) — do this before reading env vars
# ═══════════════════════════════════════════════════════════
load_dotenv(ROOT / ".env")


# ═══════════════════════════════════════════════════════════
#  LLM PROVIDER — "ollama" (local) or "gemini" (cloud)
# ═══════════════════════════════════════════════════════════
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()

# ── Ollama (local) ────────────────────────────────────────
OLLAMA_BASE         = os.getenv("OLLAMA_BASE", "http://localhost:11434")
OLLAMA_ORCHESTRATOR = os.getenv("OLLAMA_ORCHESTRATOR", "command-r7b-arabic:7b")
OLLAMA_VISION       = os.getenv("OLLAMA_VISION", "qwen3-vl:8b")
MODEL_KEEP_ALIVE    = 0   # unload immediately after each call

# ── Gemini (cloud) ────────────────────────────────────────
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_ORCHESTRATOR = os.getenv("GEMINI_ORCHESTRATOR", "gemini-3-flash-preview")
GEMINI_VISION       = os.getenv("GEMINI_VISION", "gemini-3-flash-preview")

# ── Resolve model names based on the chosen provider ──────
if LLM_PROVIDER == "gemini":
    MODEL_ORCHESTRATOR = GEMINI_ORCHESTRATOR
    MODEL_VISION       = GEMINI_VISION
else:   # ollama (default)
    MODEL_ORCHESTRATOR = OLLAMA_ORCHESTRATOR
    MODEL_VISION       = OLLAMA_VISION


# ═══════════════════════════════════════════════════════════
#  Asset search
# ═══════════════════════════════════════════════════════════
SEARCH_QUERY_PREFERENCE   = "arabic"    # "arabic" | "english" | "both"
SEARCH_FALLBACK_TO_ENGLISH = True
SEARCH_SOURCE             = "pinterest" # "pinterest" | "wikimedia" | "fbu"

PINTEREST_NUM_IMAGES       = 4
PINTEREST_MIN_RESOLUTION   = (512, 512)


# ═══════════════════════════════════════════════════════════
#  Human preview (web UI)
# ═══════════════════════════════════════════════════════════
ENABLE_PREVIEW          = True
PREVIEW_PORT            = 5173
PREVIEW_TIMEOUT_MINUTES = 20
PREVIEW_AUTO_OPEN       = True


# ═══════════════════════════════════════════════════════════
#  Recording fallback appearance
# ═══════════════════════════════════════════════════════════
RECORDING_FALLBACK_INNER_W      = 1344
RECORDING_FALLBACK_INNER_H      = 756
RECORDING_FALLBACK_BORDER       = 6
RECORDING_FALLBACK_BORDER_COLOR = "0x2a2a4e"
RECORDING_FALLBACK_BG_COLOR     = "0x0a0a1a"


# ═══════════════════════════════════════════════════════════
#  Debug / verbosity
# ═══════════════════════════════════════════════════════════
STREAM_OUTPUT = True


# ═══════════════════════════════════════════════════════════
#  Whisper (MLX, Apple Silicon)
# ═══════════════════════════════════════════════════════════
WHISPER_MODEL       = "mlx-community/whisper-large-v3-turbo"
WHISPER_LANGUAGE    = "ar"
WHISPER_TEMPERATURE = 0.0


# ═══════════════════════════════════════════════════════════
#  fast-browser-use
# ═══════════════════════════════════════════════════════════
FBU_BIN            = "fbu"
FBU_TIMEOUT        = 45
FBU_MAX_CANDIDATES = 3
ENABLE_FBU_FALLBACK = False   # slow (~45s per call); enable only when needed


# ═══════════════════════════════════════════════════════════
#  Video
# ═══════════════════════════════════════════════════════════
FPS           = 30
RESOLUTION    = "1920x1080"
VIDEO_CODEC   = "libx264"
VIDEO_PRESET  = "medium"
VIDEO_CRF     = 23
AUDIO_CODEC   = "aac"
AUDIO_BITRATE = "192k"


# ═══════════════════════════════════════════════════════════
#  Audio effects
# ═══════════════════════════════════════════════════════════
DUCK_THRESHOLD  = 0.03
DUCK_RATIO      = 8
DUCK_ATTACK     = 200
DUCK_RELEASE    = 600
BG_MUSIC_VOLUME = 0.25
NASHEED_VOLUME  = 0.35


# ═══════════════════════════════════════════════════════════
#  Fallbacks
# ═══════════════════════════════════════════════════════════
VISION_FALLBACK_TO_FIRST = True