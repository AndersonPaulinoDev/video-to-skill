import json
import zipfile

import pytest

from video_to_skill.exceptions import VideoToSkillError
from video_to_skill.generate.candidate import generate_candidate
from video_to_skill.lifecycle import approve_candidate, install_candidate, package_candidate


@pytest.fixture(autouse=True)
def isolated_approval_key(monkeypatch, tmp_path):
    monkeypatch.setenv("VIDEO_TO_SKILL_APPROVAL_KEY_FILE", str(tmp_path / "approval.key"))


def write_analysis(root):
    root.mkdir()
    (root / "manifest.json").write_text(json.dumps({
        "schema_version": 1,
        "created_at": "2026-09-01T00:00:00+00:00",
        "source_kind": "file",
        "source_display": "demo.mp4",
        "media_sha256": "a" * 64,
        "status": "extracted",
    }), encoding="utf-8")
    (root / "claims.json").write_text(json.dumps([{
        "id": "CLM-001",
        "text": "This tool always requires Python 2.",
        "evidence": ["VID-001"],
        "status": "not-researched",
    }]), encoding="utf-8")
    (root / "frames.json").write_text(json.dumps([{
        "id": "FRM-001", "timestamp": 0, "path": "frames/frame.jpg", "sha256": "b" * 64
    }]), encoding="utf-8")
    (root / "ocr.json").write_text("[]", encoding="utf-8")
    (root / "transcript.jsonl").write_text(
        json.dumps({"id": "VID-001", "start": 1, "end": 2,
                    "text": "This tool always requires Python 2."}) + "\n",
        encoding="utf-8",
    )


def write_inputs(root):
    research = root / "research.json"
    research.write_text(json.dumps({
        "sources": [{
            "id": "WEB-001",
            "title": "Current documentation",
            "url": "https://example.com/docs",
            "publisher": "Example",
        }],
        "claims": [{
            "claim_id": "CLM-001",
            "status": "conflicted",
            "current_finding": "Current releases require Python 3.",
            "evidence": ["WEB-001"],
            "confidence": "high",
        }],
    }), encoding="utf-8")
    knowledge = root / "knowledge.json"
    knowledge.write_text(json.dumps({
        "purpose": "Use the current supported runtime.",
        "topics": [{
            "title": "Runtime",
            "summary": "Use Python 3 and retain the video's outdated claim as provenance.",
            "evidence": ["VID-001", "WEB-001"],
        }],
        "procedures": [{
            "title": "Check the runtime",
            "summary": "Confirm the installed major version.",
            "evidence": ["VID-001", "WEB-001"],
            "steps": [{"text": "Run the host's version check.", "evidence": ["WEB-001"]}],
        }],
        "examples": [],
        "unresolved_questions": [],
    }), encoding="utf-8")
    return research, knowledge


def test_complete_generate_approve_install_and_package(tmp_path):
    analysis = tmp_path / "analysis"
    write_analysis(analysis)
    research, knowledge = write_inputs(tmp_path)
    candidate = tmp_path / "candidate"
    report = generate_candidate(
        analysis, candidate, "runtime-guide", "Use current runtime guidance.",
        research, knowledge,
    )
    assert report["state"] == "candidate-ready"
    assert report["approval"]["approved"] is False
    assert "Current releases require Python 3." in (candidate / "inconsistencies.md").read_text()
    assert "WEB-001" in (candidate / "sources.md").read_text()

    approved = approve_candidate(candidate, "Test User")
    assert approved["state"] == "approved"
    installed = install_candidate(candidate, tmp_path / "skills")
    assert installed.name == "runtime-guide"
    package = package_candidate(candidate, tmp_path / "runtime-guide.zip")
    with zipfile.ZipFile(package) as archive:
        assert "runtime-guide/SKILL.md" in archive.namelist()


def test_learning_mode_redacts_publication_pii_without_changing_analysis(tmp_path):
    analysis = tmp_path / "analysis"
    write_analysis(analysis)
    transcript_path = analysis / "transcript.jsonl"
    private_text = "Jane Doe always uses jane@example.com or 407-555-1212."
    transcript_path.write_text(json.dumps({
        "id": "VID-001", "start": 1, "end": 2, "text": private_text,
    }) + "\n", encoding="utf-8")
    claims_path = analysis / "claims.json"
    claims_path.write_text(json.dumps([{
        "id": "CLM-001", "text": private_text, "evidence": ["VID-001"],
        "status": "not-researched",
    }]), encoding="utf-8")
    candidate = tmp_path / "candidate"

    report = generate_candidate(
        analysis, candidate, "private-course", "Teach Jane Doe at jane@example.com.",
        mode="learning", redact_names=["Jane Doe"],
    )

    published = "\n".join(
        path.read_text(encoding="utf-8")
        for path in candidate.rglob("*") if path.is_file() and path.suffix in {".md", ".json"}
    )
    assert "Jane Doe" not in published
    assert "jane@example.com" not in published
    assert "407-555-1212" not in published
    assert "[REDACTED_NAME]" in published
    assert "[REDACTED_EMAIL]" in published
    assert (candidate / "references/learning-guide.md").is_file()
    assert report["mode"] == "learning"
    assert report["redaction"]["total_replacements"] >= 4
    assert private_text in transcript_path.read_text()


def test_pii_redaction_can_be_explicitly_disabled(tmp_path):
    analysis = tmp_path / "analysis"
    write_analysis(analysis)
    candidate = tmp_path / "candidate"

    report = generate_candidate(
        analysis, candidate, "private-reference", "Contact jane@example.com.",
        mode="reference", redact_pii=False,
    )

    assert "jane@example.com" in (candidate / "SKILL.md").read_text()
    assert report["redaction"]["enabled"] is False


def test_unresolved_claim_requires_explicit_acceptance(tmp_path):
    analysis = tmp_path / "analysis"
    write_analysis(analysis)
    candidate = tmp_path / "candidate"
    generate_candidate(analysis, candidate, "demo-skill", "Demonstrate the gate.")
    with pytest.raises(VideoToSkillError, match="unresolved"):
        approve_candidate(candidate, "Test User")
    report = approve_candidate(candidate, "Test User", accept_unresolved=True)
    assert report["approval"]["accepted_unresolved"] is True


def test_tampering_after_generation_blocks_approval(tmp_path):
    analysis = tmp_path / "analysis"
    write_analysis(analysis)
    candidate = tmp_path / "candidate"
    generate_candidate(analysis, candidate, "demo-skill", "Demonstrate integrity.")
    (candidate / "SKILL.md").write_text("tampered", encoding="utf-8")
    with pytest.raises(VideoToSkillError, match="changed"):
        approve_candidate(candidate, "Test User", accept_unresolved=True)


def test_install_before_approval_is_blocked(tmp_path):
    analysis = tmp_path / "analysis"
    write_analysis(analysis)
    candidate = tmp_path / "candidate"
    generate_candidate(analysis, candidate, "demo-skill", "Demonstrate approval.")
    with pytest.raises(VideoToSkillError, match="not approved"):
        install_candidate(candidate, tmp_path / "skills")


def test_candidate_symlink_is_rejected(tmp_path):
    analysis = tmp_path / "analysis"
    write_analysis(analysis)
    candidate = tmp_path / "candidate"
    generate_candidate(analysis, candidate, "demo-skill", "Demonstrate symlink safety.")
    (candidate / "external").symlink_to(tmp_path / "outside")
    with pytest.raises(VideoToSkillError, match="symbolic"):
        approve_candidate(candidate, "Test User", accept_unresolved=True)


def test_approval_cannot_be_reassigned(tmp_path):
    analysis = tmp_path / "analysis"
    write_analysis(analysis)
    candidate = tmp_path / "candidate"
    generate_candidate(analysis, candidate, "demo-skill", "Demonstrate immutable approval.")
    approve_candidate(candidate, "First User", accept_unresolved=True)
    with pytest.raises(VideoToSkillError, match="already approved"):
        approve_candidate(candidate, "Second User", accept_unresolved=True)


def test_forged_approval_report_is_rejected(tmp_path):
    analysis = tmp_path / "analysis"
    write_analysis(analysis)
    candidate = tmp_path / "candidate"
    generate_candidate(analysis, candidate, "demo-skill", "Demonstrate authenticated approval.")
    report_path = candidate / "generation-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["state"] = "approved"
    report["approval"].update({
        "approved": True,
        "approved_digest": report["candidate_digest"],
        "approved_by": "Forged User",
        "approved_at": "2026-09-01T00:00:00+00:00",
        "signature": "0" * 64,
    })
    report_path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(VideoToSkillError, match="Approval key|signature"):
        install_candidate(candidate, tmp_path / "skills")


def test_modified_report_name_cannot_escape_install_root(tmp_path):
    analysis = tmp_path / "analysis"
    write_analysis(analysis)
    candidate = tmp_path / "candidate"
    generate_candidate(analysis, candidate, "demo-skill", "Demonstrate path containment.")
    report_path = candidate / "generation-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["name"] = "../escaped"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(VideoToSkillError, match="invalid skill name"):
        approve_candidate(candidate, "Test User", accept_unresolved=True)


def test_preview_tampering_invalidates_candidate(tmp_path):
    analysis = tmp_path / "analysis"
    write_analysis(analysis)
    candidate = tmp_path / "candidate"
    generate_candidate(analysis, candidate, "demo-skill", "Demonstrate preview integrity.")
    (candidate / "PREVIEW.md").write_text("misleading preview", encoding="utf-8")
    with pytest.raises(VideoToSkillError, match="changed"):
        approve_candidate(candidate, "Test User", accept_unresolved=True)


def test_approved_report_provenance_tampering_is_rejected(tmp_path):
    analysis = tmp_path / "analysis"
    write_analysis(analysis)
    candidate = tmp_path / "candidate"
    generate_candidate(analysis, candidate, "demo-skill", "Demonstrate report integrity.")
    approve_candidate(candidate, "Test User", accept_unresolved=True)
    report_path = candidate / "generation-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["source"]["display"] = "forged-source.mp4"
    report["counts"]["claims"] = 999
    report_path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(VideoToSkillError, match="signature"):
        package_candidate(candidate, tmp_path / "forged.zip")


def test_approval_receipt_tampering_is_rejected(tmp_path):
    analysis = tmp_path / "analysis"
    write_analysis(analysis)
    candidate = tmp_path / "candidate"
    generate_candidate(analysis, candidate, "demo-skill", "Demonstrate receipt integrity.")
    approve_candidate(candidate, "Test User", accept_unresolved=True)
    (candidate / "APPROVAL.md").write_text("Approved by Mallory", encoding="utf-8")
    with pytest.raises(VideoToSkillError, match="receipt"):
        package_candidate(candidate, tmp_path / "forged.zip")
