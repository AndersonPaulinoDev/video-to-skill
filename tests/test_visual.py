import json
import shutil
import subprocess

import pytest

from video_to_skill.exceptions import VideoToSkillError
from video_to_skill.extract.visual import inspect_frame, inspect_window, parse_timestamp
from video_to_skill.provenance import sha256_file


def test_parse_timestamp_formats_and_rejects_invalid_values():
    assert parse_timestamp("90.5") == 90.5
    assert parse_timestamp("01:30") == 90.0
    assert parse_timestamp("01:02:03.5") == 3723.5
    with pytest.raises(VideoToSkillError):
        parse_timestamp("1:99")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg unavailable")
def test_reinspection_is_bounded_and_reusable(tmp_path):
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    video = analysis / "source.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
        "testsrc=size=160x120:rate=10:duration=8", "-pix_fmt", "yuv420p", str(video),
    ], check=True)
    (analysis / "manifest.json").write_text(json.dumps({
        "working_media": "source.mp4",
        "media_sha256": sha256_file(video),
        "probe": {"duration_seconds": 8.0},
    }), encoding="utf-8")
    (analysis / "frames.json").write_text("[]", encoding="utf-8")

    exact = inspect_frame(analysis, "00:01.5")
    window = inspect_window(analysis, "0", "8", 10.0)

    assert len(exact["frames"]) == 1
    assert window["requested_frames"] == 80
    assert len(window["frames"]) == 60
    assert window["truncated"] is True
    assert (analysis / exact["frames"][0]["path"]).is_file()


def test_reinspection_rejects_replaced_media(tmp_path):
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    video = analysis / "source.mp4"
    video.write_bytes(b"original-media")
    (analysis / "manifest.json").write_text(json.dumps({
        "working_media": "source.mp4",
        "media_sha256": sha256_file(video),
        "probe": {"duration_seconds": 8.0},
    }), encoding="utf-8")
    (analysis / "frames.json").write_text("[]", encoding="utf-8")
    video.write_bytes(b"replacement-media")

    with pytest.raises(VideoToSkillError, match="source digest"):
        inspect_frame(analysis, "1")
    with pytest.raises(VideoToSkillError, match="source digest"):
        inspect_window(analysis, "0", "2", 1.0)
