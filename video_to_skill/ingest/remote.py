import json
import shutil
import subprocess
import sys
from importlib.util import find_spec
from pathlib import Path

from ..exceptions import VideoToSkillError

def acquire_url(url: str, workdir: Path) -> tuple[Path, dict]:
    template = str(workdir / "source.%(ext)s")
    if shutil.which("yt-dlp"):
        runner = ["yt-dlp"]
    elif find_spec("yt_dlp") is not None:
        runner = [sys.executable, "-m", "yt_dlp"]
    else:
        raise VideoToSkillError("URL support requires yt-dlp")
    command = runner + ["--no-playlist", "--write-info-json", "--write-subs",
               "--write-auto-subs", "--sub-langs", "all,-live_chat", "-o", template, url]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "yt-dlp failed").strip()
        raise VideoToSkillError(message[-2000:]) from exc
    excluded = {".json", ".vtt", ".srt", ".part"}
    media = [p for p in workdir.glob("source.*") if p.suffix not in excluded]
    if not media:
        raise VideoToSkillError("The URL did not produce a video file")
    info = workdir / "source.info.json"
    metadata = json.loads(info.read_text(encoding="utf-8")) if info.exists() else {}
    return media[0], metadata
