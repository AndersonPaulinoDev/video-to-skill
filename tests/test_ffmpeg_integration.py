import shutil
import subprocess
from pathlib import Path

import pytest

from video_to_skill.extract.media import extract_frames, probe_media

@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg unavailable")
def test_frame_sampling_never_seeks_to_exact_end(tmp_path):
    video = tmp_path / "sample.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
        "color=c=blue:s=160x120:d=2", "-c:v", "libx264", str(video)
    ], check=True)
    duration = probe_media(video)["duration_seconds"]
    frames = extract_frames(video, tmp_path / "frames", duration, 1.0, 3)
    assert len(frames) == 1
    assert all(Path(item["path"]).is_file() for item in frames)


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg unavailable")
def test_scene_changes_add_frames_and_remove_duplicates(tmp_path):
    video = tmp_path / "cuts.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "color=red:s=160x120:d=1",
        "-f", "lavfi", "-i", "color=green:s=160x120:d=1",
        "-f", "lavfi", "-i", "color=blue:s=160x120:d=1",
        "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0,format=yuv420p[v]",
        "-map", "[v]", str(video),
    ], check=True)
    duration = probe_media(video)["duration_seconds"]

    frames = extract_frames(video, tmp_path / "cuts", duration, 10.0, 10, 0.2, 6.0)

    assert len(frames) == 3
    assert sum(item["selection"] == "scene-change" for item in frames) == 2
