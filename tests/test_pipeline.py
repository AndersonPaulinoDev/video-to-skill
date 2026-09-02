import json

from video_to_skill.pipeline import analyze

def test_pipeline_writes_evidence_contract(monkeypatch, tmp_path):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"video-data")
    subtitle = tmp_path / "source.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nThis is current.\n", encoding="utf-8")
    output = tmp_path / "work"

    monkeypatch.setattr("video_to_skill.pipeline.probe_media", lambda _: {"duration_seconds": 1.0})
    def fake_frames(_, directory, duration, interval, max_frames, *args):
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
    assert manifest["schema_version"] == 2
    assert manifest["processing"]["resumable_workspace"] is True
    assert (output / "claims.json").is_file()


def test_completed_analysis_resumes_without_repeating_extraction(monkeypatch, tmp_path):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"video-data")
    (tmp_path / "source.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nResume safely.\n", encoding="utf-8"
    )
    output = tmp_path / "work"
    monkeypatch.setattr("video_to_skill.pipeline.probe_media", lambda _: {"duration_seconds": 1.0})

    def fake_frames(_, directory, *args):
        directory.mkdir(parents=True)
        frame = directory / "frame.jpg"
        frame.write_bytes(b"frame")
        return [{"id": "FRM-001", "timestamp": 0.0, "path": str(frame), "selection": "periodic"}]

    monkeypatch.setattr("video_to_skill.pipeline.extract_frames", fake_frames)
    monkeypatch.setattr("video_to_skill.pipeline.ocr_frames", lambda *_: [])
    first = analyze(str(video), output)
    monkeypatch.setattr(
        "video_to_skill.pipeline.probe_media",
        lambda _: (_ for _ in ()).throw(AssertionError("probe must not repeat")),
    )
    monkeypatch.setattr(
        "video_to_skill.pipeline.extract_frames",
        lambda *_: (_ for _ in ()).throw(AssertionError("frames must not repeat")),
    )

    resumed = analyze(str(video), output, resume=True)

    assert resumed == first
    progress = json.loads((output / "progress.json").read_text())
    assert progress["percent_complete"] == 100.0


def test_resume_rejects_changed_settings(monkeypatch, tmp_path):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"video-data")
    (tmp_path / "source.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nKeep settings stable.\n", encoding="utf-8"
    )
    output = tmp_path / "work"
    monkeypatch.setattr("video_to_skill.pipeline.probe_media", lambda _: {"duration_seconds": 1.0})

    def fake_frames(_, directory, *args):
        directory.mkdir(parents=True)
        frame = directory / "frame.jpg"
        frame.write_bytes(b"frame")
        return [{"id": "FRM-001", "timestamp": 0.0, "path": str(frame)}]

    monkeypatch.setattr("video_to_skill.pipeline.extract_frames", fake_frames)
    monkeypatch.setattr("video_to_skill.pipeline.ocr_frames", lambda *_: [])
    analyze(str(video), output)

    from video_to_skill.exceptions import VideoToSkillError
    import pytest

    with pytest.raises(VideoToSkillError, match="settings do not match"):
        analyze(str(video), output, frame_interval=30.0, resume=True)


def test_interrupted_analysis_resumes_from_failed_stage(monkeypatch, tmp_path):
    import pytest

    video = tmp_path / "source.mp4"
    video.write_bytes(b"video-data")
    (tmp_path / "source.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nRecover this run.\n", encoding="utf-8"
    )
    output = tmp_path / "work"
    monkeypatch.setattr("video_to_skill.pipeline.probe_media", lambda _: {"duration_seconds": 1.0})
    monkeypatch.setattr(
        "video_to_skill.pipeline.extract_frames",
        lambda *_: (_ for _ in ()).throw(RuntimeError("simulated interruption")),
    )
    with pytest.raises(RuntimeError, match="simulated interruption"):
        analyze(str(video), output)
    interrupted = json.loads((output / "progress.json").read_text())
    assert [stage["status"] for stage in interrupted["stages"][:4]] == [
        "complete", "complete", "complete", "failed"
    ]

    def recovered_frames(_, directory, *args):
        directory.mkdir(parents=True, exist_ok=True)
        frame = directory / "recovered.jpg"
        frame.write_bytes(b"frame")
        return [{"id": "FRM-001", "timestamp": 0.0, "path": str(frame)}]

    monkeypatch.setattr("video_to_skill.pipeline.extract_frames", recovered_frames)
    monkeypatch.setattr("video_to_skill.pipeline.ocr_frames", lambda *_: [])
    monkeypatch.setattr(
        "video_to_skill.pipeline.probe_media",
        lambda _: (_ for _ in ()).throw(AssertionError("completed probe must be reused")),
    )
    preview = analyze(str(video), output, resume=True)

    assert preview["state"] == "analysis-ready"
    completed = json.loads((output / "progress.json").read_text())
    assert completed["percent_complete"] == 100.0
