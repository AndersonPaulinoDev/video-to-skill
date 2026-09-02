import math
import shutil
import subprocess
from pathlib import Path

from ..exceptions import VideoToSkillError
from ..provenance import sha256_file, write_json


MAX_REINSPECTION_FRAMES = 60
_TINY_FRAME_BYTES = 9 * 8 * 3


def parse_timestamp(value: str) -> float:
    parts = value.strip().split(":")
    if not 1 <= len(parts) <= 3:
        raise VideoToSkillError("Timestamp must use seconds, MM:SS, or HH:MM:SS")
    try:
        numbers = [float(part) for part in parts]
    except ValueError as exc:
        raise VideoToSkillError(f"Invalid timestamp: {value}") from exc
    if any(number < 0 or not math.isfinite(number) for number in numbers):
        raise VideoToSkillError(f"Invalid timestamp: {value}")
    if len(numbers) == 1:
        return numbers[0]
    if numbers[-1] >= 60 or (len(numbers) == 3 and numbers[-2] >= 60):
        raise VideoToSkillError(f"Invalid timestamp: {value}")
    return sum(number * multiplier for number, multiplier in zip(reversed(numbers), (1, 60, 3600)))


def scene_timestamps(path: Path, duration: float, threshold: float = 0.32,
                     maximum: int = 120) -> list[float]:
    if not 0 < threshold < 1:
        raise VideoToSkillError("Scene threshold must be between 0 and 1")
    sampling_fps = min(2.0, max(0.1, 7200 / max(duration, 0.1)))
    command = [
        "ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-an",
        "-vf", f"fps={sampling_fps},scale=9:8", "-pix_fmt", "rgb24", "-f", "rawvideo", "-",
    ]
    try:
        result = subprocess.run(command, check=False, capture_output=True)
    except FileNotFoundError as exc:
        raise VideoToSkillError("ffmpeg is required to detect scene changes") from exc
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise VideoToSkillError(message or "Scene detection failed")
    thumbnails = [
        result.stdout[offset:offset + _TINY_FRAME_BYTES]
        for offset in range(0, len(result.stdout), _TINY_FRAME_BYTES)
        if len(result.stdout[offset:offset + _TINY_FRAME_BYTES]) == _TINY_FRAME_BYTES
    ]
    found = []
    if not thumbnails:
        return found
    anchor = thumbnails[0]
    for index in range(1, len(thumbnails)):
        previous = thumbnails[index - 1]
        current = thumbnails[index]
        changed = max(mean_difference(current, previous), mean_difference(current, anchor)) / 255
        if changed > threshold:
            timestamp = index / sampling_fps
            found.append(timestamp)
            anchor = current
            if len(found) >= maximum:
                break
    return found


def frame_signature(path: Path) -> bytes:
    command = [
        "ffmpeg", "-v", "error", "-i", str(path), "-vf", "scale=9:8",
        "-pix_fmt", "rgb24", "-frames:v", "1", "-f", "rawvideo", "-",
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise VideoToSkillError(f"Could not fingerprint frame: {path.name}") from exc
    if len(result.stdout) != _TINY_FRAME_BYTES:
        raise VideoToSkillError(f"Frame fingerprint had an unexpected size: {path.name}")
    return result.stdout


def mean_difference(left: bytes, right: bytes) -> float:
    return sum(abs(a - b) for a, b in zip(left, right)) / len(left)


def deduplicate_frames(records: list[dict], threshold: float = 6.0) -> list[dict]:
    kept = []
    signatures = []
    for record in records:
        signature = frame_signature(Path(record["path"]))
        if any(mean_difference(signature, prior) <= threshold for prior in signatures):
            Path(record["path"]).unlink(missing_ok=True)
            continue
        signatures.append(signature)
        kept.append(record)
    for index, record in enumerate(kept, 1):
        record["id"] = f"FRM-{index:03d}"
    return kept


def resolve_working_media(analysis: Path, manifest: dict) -> Path:
    value = Path(manifest["working_media"])
    media = value if value.is_absolute() else analysis / value
    if not media.is_file():
        raise VideoToSkillError(f"Working media is unavailable: {media}")
    expected_digest = manifest.get("media_sha256")
    if not expected_digest or sha256_file(media) != expected_digest:
        raise VideoToSkillError("Working media no longer matches the analyzed source digest")
    return media


def reinspection_frames(analysis: Path, media: Path, timestamps: list[float]) -> list[dict]:
    target_root = analysis / "reinspection"
    target_root.mkdir(parents=True, exist_ok=True)
    records = []
    for timestamp in timestamps:
        millis = round(timestamp * 1000)
        target = target_root / f"frame-{millis:012d}ms.jpg"
        if not target.is_file():
            _extract_frame(media, timestamp, target)
        records.append({
            "timestamp": timestamp,
            "path": str(target.relative_to(analysis)),
            "selection": "investigation",
            "sha256": sha256_file(target),
        })
    return _promote_reinspection(analysis, records)


def _promote_reinspection(analysis: Path, records: list[dict]) -> list[dict]:
    frames_path = analysis / "frames.json"
    if not frames_path.is_file():
        raise VideoToSkillError("Analysis frames.json is unavailable")
    import json

    frames = json.loads(frames_path.read_text(encoding="utf-8"))
    if not isinstance(frames, list):
        raise VideoToSkillError("Analysis frames.json must contain an array")
    by_path = {item.get("path"): item for item in frames}
    next_number = max(
        (int(item["id"].split("-")[-1]) for item in frames if str(item.get("id", "")).startswith("FRM-")),
        default=0,
    ) + 1
    promoted = []
    for record in records:
        existing = by_path.get(record["path"])
        if existing:
            promoted.append(existing)
            continue
        record["id"] = f"FRM-{next_number:03d}"
        next_number += 1
        frames.append(record)
        by_path[record["path"]] = record
        promoted.append(record)
    write_json(frames_path, frames)
    preview_path = analysis / "preview.json"
    if preview_path.is_file():
        preview = json.loads(preview_path.read_text(encoding="utf-8"))
        preview.setdefault("evidence", {})["sampled_frames"] = len(frames)
        write_json(preview_path, preview)
    from ..workspace import Workspace

    workspace = Workspace(analysis)
    if workspace.database.is_file():
        workspace.complete("frames", {
            "frame_count": len(frames),
            "periodic": sum(item.get("selection") == "periodic" for item in frames),
            "scene_changes": sum(item.get("selection") == "scene-change" for item in frames),
            "investigation": sum(item.get("selection") == "investigation" for item in frames),
        })
    return promoted


def inspect_frame(analysis: Path, timestamp: str) -> dict:
    import json

    manifest = json.loads((analysis / "manifest.json").read_text(encoding="utf-8"))
    seconds = parse_timestamp(timestamp)
    duration = float(manifest["probe"]["duration_seconds"])
    if seconds >= duration:
        raise VideoToSkillError("Requested timestamp is outside the video")
    return {"frames": reinspection_frames(analysis, resolve_working_media(analysis, manifest), [seconds])}


def inspect_window(analysis: Path, start: str, end: str, fps: float) -> dict:
    import json

    if not 0 < fps <= 10:
        raise VideoToSkillError("Reinspection FPS must be between 0 and 10")
    manifest = json.loads((analysis / "manifest.json").read_text(encoding="utf-8"))
    duration = float(manifest["probe"]["duration_seconds"])
    first, last = parse_timestamp(start), parse_timestamp(end)
    if last <= first or first >= duration:
        raise VideoToSkillError("Reinspection window must be within the video and end after it starts")
    last = min(last, duration)
    requested = max(1, math.ceil((last - first) * fps))
    count = min(requested, MAX_REINSPECTION_FRAMES)
    timestamps = [first + index / fps for index in range(count)]
    return {
        "frames": reinspection_frames(analysis, resolve_working_media(analysis, manifest), timestamps),
        "requested_frames": requested,
        "truncated": requested > MAX_REINSPECTION_FRAMES,
    }


def _extract_frame(media: Path, timestamp: float, target: Path) -> None:
    if not shutil.which("ffmpeg"):
        raise VideoToSkillError("ffmpeg is required to inspect video frames")
    command = [
        "ffmpeg", "-y", "-v", "error", "-ss", str(timestamp), "-i", str(media),
        "-frames:v", "1", "-vf", "scale='min(1280,iw)':-2", "-q:v", "2", str(target),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        raise VideoToSkillError(f"Frame reinspection failed at {timestamp:.3f}s") from exc
