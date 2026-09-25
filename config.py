"""All pipeline settings in one place. Edit here, not scattered in code."""

from pathlib import Path

# --- Paths ---
FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
ROOT = Path(__file__).parent
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"
WORKSPACE_DIR = ROOT / "workspace"
MODELS_DIR = ROOT / "models"

BG_MUSIC_DIR = ASSETS_DIR / "bg_music"
NASHEED_DIR = ASSETS_DIR / "nasheed"
# --- Debug / verbosity ---
STREAM_OUTPUT = True    # print model tokens live as they arrive
# Default input video (used if none passed via CLI)
DEFAULT_VIDEO = INPUT_DIR / "recording.mp4"

# Output subfolders
TRANSCRIPT_DIR = OUTPUT_DIR / "transcript"
PLAN_DIR = OUTPUT_DIR / "plan"
SCENE_ASSETS_DIR = OUTPUT_DIR / "assets"
CLIPS_DIR = OUTPUT_DIR / "clips"
FINAL_DIR = OUTPUT_DIR / "final"

# --- Ollama ---
OLLAMA_BASE = "http://localhost:11434"
MODEL_ORCHESTRATOR = "command-r7b-arabic:7b"
MODEL_VISION = "qwen2.5vl:7b"
MODEL_KEEP_ALIVE = 0          # unload immediately after each call

# --- Whisper (MLX, Apple Silicon) ---
WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
WHISPER_LANGUAGE = "ar"
WHISPER_TEMPERATURE = 0.0
# --- fast-browser-use ---
FBU_BIN = "fbu"
FBU_TIMEOUT = 180
FBU_MAX_CANDIDATES = 3

# --- Video ---
FPS = 30
RESOLUTION = "1920x1080"
VIDEO_CODEC = "libx264"
VIDEO_PRESET = "medium"
VIDEO_CRF = 23
AUDIO_CODEC = "aac"
AUDIO_BITRATE = "192k"

# --- Audio effects ---
DUCK_THRESHOLD = 0.03
DUCK_RATIO = 8
DUCK_ATTACK = 200
DUCK_RELEASE = 600
BG_MUSIC_VOLUME = 0.25
NASHEED_VOLUME = 0.35

# --- Fallbacks ---
VISION_FALLBACK_TO_FIRST = True   # if vision judge fails, pick first image