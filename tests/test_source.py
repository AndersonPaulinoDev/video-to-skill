from pathlib import Path

import pytest

from video_to_skill.exceptions import VideoToSkillError
from video_to_skill.ingest.source import resolve_source

def test_local_video(tmp_path: Path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    source = resolve_source(str(video))
    assert source.kind == "file"
    assert source.local_path == video.resolve()

def test_public_url():
    source = resolve_source("https://example.com/video")
    assert source.kind == "url"

@pytest.mark.parametrize("value", ["ftp://example.com/a.mp4", "https://user:pass@example.com/a.mp4"])
def test_unsafe_url_rejected(value):
    with pytest.raises(VideoToSkillError):
        resolve_source(value)

def test_wrong_extension_rejected(tmp_path: Path):
    value = tmp_path / "notes.txt"
    value.write_text("not video", encoding="utf-8")
    with pytest.raises(VideoToSkillError):
        resolve_source(str(value))

