from pathlib import Path

SUPPORTED_LOCAL_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpeg", ".mpg"
}
ALLOWED_URL_SCHEMES = {"http", "https"}
DEFAULT_FRAME_INTERVAL = 60.0
MAX_FRAMES = 120

def expand_path(value: str) -> Path:
    return Path(value).expanduser().resolve()

