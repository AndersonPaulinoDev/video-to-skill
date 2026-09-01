import json
import math
import subprocess
from pathlib import Path

from ..exceptions import VideoToSkillError

def probe_media(path: Path) -> dict:
    command = ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise VideoToSkillError("ffprobe is required to inspect video files") from exc
    except subprocess.CalledProcessError as exc:
        raise VideoToSkillError((exc.stderr or "ffprobe failed").strip()) from exc
    data = json.loads(result.stdout)
    try:
        data["duration_seconds"] = float(data.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        data["duration_seconds"] = 0.0
    return data

def extract_audio(path: Path, target: Path) -> Path:
    command = ["ffmpeg", "-y", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", str(target)]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise VideoToSkillError("ffmpeg is required to extract audio") from exc
    except subprocess.CalledProcessError as exc:
        raise VideoToSkillError((exc.stderr or "audio extraction failed").strip()) from exc
    return target

def extract_frames(path: Path, directory: Path, duration: float, interval: float, max_frames: int) -> list[dict]:
    directory.mkdir(parents=True, exist_ok=True)
    count = min(max_frames, max(1, math.ceil(duration / interval))) if duration > 0 else 1
    timestamps = [i * interval for i in range(count)] if duration > 0 else [0.0]
    records = []
    for index, timestamp in enumerate(timestamps, 1):
        target = directory / f"frame-{index:03d}-{int(timestamp):06d}s.jpg"
        command = ["ffmpeg", "-y", "-v", "error", "-ss", str(timestamp), "-i", str(path),
                   "-frames:v", "1", "-q:v", "2", str(target)]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            raise VideoToSkillError(f"Frame extraction failed at {timestamp:.1f}s") from exc
        if not target.is_file():
            raise VideoToSkillError(f"Frame extraction produced no image at {timestamp:.1f}s")
        records.append({"id": f"FRM-{index:03d}", "timestamp": timestamp, "path": str(target)})
    return records
