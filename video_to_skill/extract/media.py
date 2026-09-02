import json
import math
import subprocess
from pathlib import Path

from ..exceptions import VideoToSkillError
from .visual import deduplicate_frames, scene_timestamps

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

def extract_frames(path: Path, directory: Path, duration: float, interval: float, max_frames: int,
                   scene_threshold: float = 0.32, dedup_threshold: float = 6.0) -> list[dict]:
    directory.mkdir(parents=True, exist_ok=True)
    count = min(max_frames, max(1, math.ceil(duration / interval))) if duration > 0 else 1
    periodic = [round(i * interval, 3) for i in range(count)] if duration > 0 else [0.0]
    scenes = scene_timestamps(path, duration, scene_threshold, max_frames) if duration > 0 else []
    candidates = sorted({round(value, 3) for value in periodic + scenes})
    if len(candidates) <= max_frames:
        timestamps = candidates
    elif max_frames == 1:
        timestamps = [candidates[0]]
    else:
        timestamps = [
            candidates[round(index * (len(candidates) - 1) / (max_frames - 1))]
            for index in range(max_frames)
        ]
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
        kind = "periodic" if timestamp in periodic else "scene-change"
        records.append({
            "id": f"FRM-{index:03d}", "timestamp": timestamp, "path": str(target),
            "selection": kind,
        })
    return deduplicate_frames(records, dedup_threshold)
