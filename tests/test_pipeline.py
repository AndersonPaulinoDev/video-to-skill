import json

from video_to_skill.pipeline import analyze

def test_pipeline_writes_evidence_contract(monkeypatch, tmp_path):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"video-data")
    subtitle = tmp_path / "source.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nThis is current.\n", encoding="utf-8")
    output = tmp_path / "work"

    monkeypatch.setattr("video_to_skill.pipeline.probe_media", lambda _: {"duration_seconds": 1.0})
    def fake_frames(_, directory, duration, interval, max_frames):
        directory.mkdir(parents=True)
        frame = directory / "frame.jpg"
        frame.write_bytes(b"frame")
        return [{"id": "FRM-001", "timestamp": 0.0, "path": str(frame)}]
    monkeypatch.setattr("video_to_skill.pipeline.extract_frames", fake_frames)
    monkeypatch.setattr("video_to_skill.pipeline.ocr_frames", lambda *_: [])

    preview = analyze(str(video), output)
    assert preview["evidence"]["transcript_cues"] == 1
    assert preview["install_or_publish_allowed"] is False
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "extracted"
    assert (output / "claims.json").is_file()
