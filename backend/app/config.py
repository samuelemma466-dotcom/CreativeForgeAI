from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

APP_NAME = "CreativeForge AI"
APP_VERSION = "0.1.0"
REPO_ROOT = Path(os.environ.get("CFAI_ROOT", Path(__file__).resolve().parents[2])).resolve()

DATA_DIR = Path(os.environ.get("CFAI_DATA_DIR", REPO_ROOT / "data")).resolve()
MEDIA_ROOT = Path(os.environ.get("CFAI_MEDIA_DIR", REPO_ROOT / "media")).resolve()
UPLOAD_DIR = MEDIA_ROOT / "uploads"
PROJECT_MEDIA_DIR = MEDIA_ROOT / "projects"
EXPORT_DIR = MEDIA_ROOT / "exports"
PREVIEW_DIR = MEDIA_ROOT / "previews"
VOICE_DIR = MEDIA_ROOT / "voice"
DB_PATH = Path(os.environ.get("CFAI_DB_PATH", DATA_DIR / "creativeforge.db")).resolve()
SECRETS_PATH = Path(os.environ.get("CFAI_SECRETS_PATH", DATA_DIR / "secrets.json")).resolve()

API_HOST = os.environ.get("CFAI_API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("CFAI_API_PORT", "8787"))
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CFAI_FRONTEND_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    ).split(",")
    if origin.strip()
]

OLLAMA_DEFAULT_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT_SECONDS = float(os.environ.get("CFAI_OLLAMA_TIMEOUT", "240"))
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_TIMEOUT_SECONDS = float(os.environ.get("CFAI_OPENROUTER_TIMEOUT", "120"))
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_TIMEOUT_SECONDS = float(os.environ.get("CFAI_GEMINI_TIMEOUT", "120"))
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_TIMEOUT_SECONDS = float(os.environ.get("CFAI_GROQ_TIMEOUT", "120"))

MAX_IMAGE_BYTES = int(os.environ.get("CFAI_MAX_IMAGE_BYTES", str(30 * 1024 * 1024)))
MAX_AUDIO_BYTES = int(os.environ.get("CFAI_MAX_AUDIO_BYTES", str(50 * 1024 * 1024)))
MAX_VIDEO_BYTES = int(os.environ.get("CFAI_MAX_VIDEO_BYTES", str(400 * 1024 * 1024)))
MAX_UPLOAD_BYTES = max(MAX_IMAGE_BYTES, MAX_AUDIO_BYTES, MAX_VIDEO_BYTES)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}

FONT_DIR = Path("/usr/share/fonts/liberation")
FONTS = {
    "sans": FONT_DIR / "LiberationSans-Regular.ttf",
    "sans_bold": FONT_DIR / "LiberationSans-Bold.ttf",
    "serif": FONT_DIR / "LiberationSerif-Regular.ttf",
    "serif_bold": FONT_DIR / "LiberationSerif-Bold.ttf",
    "mono": FONT_DIR / "LiberationMono-Regular.ttf",
    "mono_bold": FONT_DIR / "LiberationMono-Bold.ttf",
}
FONT_FALLBACK = Path("/usr/share/fonts/TTF/LiberationSans-Regular.ttf")
FFMPEG = os.environ.get("CFAI_FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("CFAI_FFPROBE", "ffprobe")
ESPEAK = os.environ.get("CFAI_ESPEAK", "espeak-ng")

TEMP_DIR = Path(os.environ.get("CFAI_TEMP_DIR", REPO_ROOT / "media" / "projects" / "tmp")).resolve()


def ensure_directories() -> None:
    for directory in (
        DATA_DIR,
        MEDIA_ROOT,
        UPLOAD_DIR,
        PROJECT_MEDIA_DIR,
        EXPORT_DIR,
        PREVIEW_DIR,
        VOICE_DIR,
        TEMP_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
