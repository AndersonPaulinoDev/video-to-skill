import shutil
from importlib.util import find_spec

COMMANDS = ("ffmpeg", "ffprobe", "yt-dlp", "whisper", "tesseract")

def capability_report() -> dict:
    commands = {name: shutil.which(name) for name in COMMANDS}
    modules = {name: find_spec(name) is not None for name in ("yt_dlp", "faster_whisper")}
    return {
        "commands": commands,
        "python_modules": modules,
        "ready_for_local_video": bool(commands["ffmpeg"] and commands["ffprobe"]),
        "ready_for_url": bool(commands["yt-dlp"] or modules["yt_dlp"]),
        "ready_for_transcription": bool(commands["whisper"] or modules["faster_whisper"]),
        "ready_for_ocr": bool(commands["tesseract"]),
    }

