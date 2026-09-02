import json
from pathlib import Path

import pytest

from video_to_skill.course import analyze_course, inventory_course, merge_analyses
from video_to_skill.exceptions import VideoToSkillError
from video_to_skill.generate.candidate import generate_candidate
from video_to_skill.lifecycle import approve_candidate


def write_analysis(root: Path, source: str, cue_texts: list[str]):
    root.mkdir()
    frames = root / "frames"
    frames.mkdir()
    (frames / "frame.jpg").write_bytes(source.encode())
    (root / "manifest.json").write_text(json.dumps({
        "schema_version": 2,
        "created_at": "2026-09-02T00:00:00+00:00",
        "source_kind": "file",
        "source_display": source,
        "media_sha256": source * 4,
        "probe": {"duration_seconds": 2},
        "status": "extracted",
    }), encoding="utf-8")
    cues = [
        {"id": f"VID-{index:03d}", "start": index - 1, "end": index, "text": text}
        for index, text in enumerate(cue_texts, 1)
    ]
    (root / "transcript.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in cues), encoding="utf-8"
    )
    (root / "frames.json").write_text(json.dumps([{
        "id": "FRM-001", "timestamp": 0, "path": "frames/frame.jpg", "sha256": "b" * 64,
    }]), encoding="utf-8")
    (root / "ocr.json").write_text("[]", encoding="utf-8")
    (root / "claims.json").write_text(json.dumps([
        {
            "id": f"CLM-{index:03d}", "text": text, "evidence": [f"VID-{index:03d}"],
            "status": "not-researched",
        }
        for index, text in enumerate(cue_texts, 1)
    ]), encoding="utf-8")


def test_local_inventory_is_normalized(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "input.json"
    source.write_text(json.dumps({
        "title": "Course",
        "sources": [{"source": "one.mp4"}, {"id": "SRC-002", "source": "two.mp4"}],
    }), encoding="utf-8")

    inventory = inventory_course(str(source), tmp_path / "normalized/inventory.json")

    assert [item["id"] for item in inventory["sources"]] == ["SRC-001", "SRC-002"]
    assert inventory["sources"][0]["source"] == str(source_dir / "one.mp4")
    assert inventory["sources"][1]["source"] == str(source_dir / "two.mp4")
    assert (tmp_path / "normalized/inventory.json").is_file()


def test_merge_preserves_sources_deduplicates_agreements_and_keeps_conflicts(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_analysis(first, "a" * 16, ["Safe mode is always required."])
    write_analysis(second, "b" * 16, [
        "Safe mode is always required.", "Safe mode is never required.",
    ])

    preview = merge_analyses([first, second], tmp_path / "merged", "Safety course")
    claims = json.loads((tmp_path / "merged/claims.json").read_text())
    cues = [json.loads(line) for line in (tmp_path / "merged/transcript.jsonl").read_text().splitlines()]

    assert preview["evidence"]["source_count"] == 2
    assert len(cues) == 3
    assert len(claims) == 2
    assert claims[0]["source_ids"] == ["SRC-001", "SRC-002"]
    assert claims[0]["evidence"] == ["VID-001", "VID-002"]
    assert claims[1]["text"] == "Safe mode is never required."
    assert len(list((tmp_path / "merged/frames").iterdir())) == 2


def test_merge_rejects_frame_path_escape(tmp_path):
    analysis = tmp_path / "analysis"
    write_analysis(analysis, "a" * 16, ["A claim is always true."])
    frames = json.loads((analysis / "frames.json").read_text())
    frames[0]["path"] = "../outside.jpg"
    (analysis / "frames.json").write_text(json.dumps(frames), encoding="utf-8")
    (tmp_path / "outside.jpg").write_bytes(b"outside")

    with pytest.raises(VideoToSkillError, match="escapes"):
        merge_analyses([analysis], tmp_path / "merged")


def test_incomplete_course_remains_visible_and_requires_acceptance(monkeypatch, tmp_path):
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps({
        "title": "Partial course",
        "sources": [
            {"id": "SRC-001", "source": "missing.mp4", "title": "Missing"},
            {"id": "SRC-002", "source": "available.mp4", "title": "Available"},
        ],
    }), encoding="utf-8")

    def fake_analyze(source, output, *args):
        if source.endswith("missing.mp4"):
            raise VideoToSkillError(f"unavailable private path: {source}")
        write_analysis(output, "a" * 16, [])
        return {"state": "analysis-ready"}

    monkeypatch.setattr("video_to_skill.course.analyze", fake_analyze)
    report = analyze_course(inventory, tmp_path / "course")
    candidate = tmp_path / "candidate"
    generated = generate_candidate(
        tmp_path / "course/merged", candidate, "partial-course", "Use the available lessons."
    )

    assert report["complete"] is False
    assert generated["unresolved_sources"] == ["SRC-001"]
    merged_manifest = json.loads((tmp_path / "course/merged/manifest.json").read_text())
    assert merged_manifest["sources"][0]["id"] == "SRC-002"
    assert merged_manifest["sources"][0]["display"] == "Available"
    assert str(tmp_path) not in (candidate / "generation-report.json").read_text()
    assert "1/2 completed" in (candidate / "PREVIEW.md").read_text()
    with pytest.raises(VideoToSkillError, match="unresolved"):
        approve_candidate(candidate, "Reviewer")
