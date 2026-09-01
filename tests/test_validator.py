import importlib.util
import json
from pathlib import Path

import pytest

from video_to_skill.generate.candidate import candidate_digest
from video_to_skill.lifecycle import approve_candidate

MODULE_PATH = Path(__file__).parents[1] / "tools" / "validate_generated_skill.py"
SPEC = importlib.util.spec_from_file_location("validator", MODULE_PATH)
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validator)

@pytest.fixture(autouse=True)
def isolated_approval_key(monkeypatch, tmp_path):
    key = tmp_path.parent / f"{tmp_path.name}-approval.key"
    monkeypatch.setenv("VIDEO_TO_SKILL_APPROVAL_KEY_FILE", str(key))

def candidate(tmp_path: Path) -> Path:
    (tmp_path / "SKILL.md").write_text("---\nname: demo\ndescription: demo\n---\n", encoding="utf-8")
    (tmp_path / "sources.md").write_text("# Sources\n", encoding="utf-8")
    (tmp_path / "claims.md").write_text("# Claims\nSupported by VID-001.\n", encoding="utf-8")
    (tmp_path / "inconsistencies.md").write_text("# Inconsistencies\nNone identified.\n", encoding="utf-8")
    report_path = tmp_path / "generation-report.json"
    report_path.write_text("{}", encoding="utf-8")
    report = {
        "state": "candidate-ready",
        "name": "demo-skill",
        "candidate_digest": candidate_digest(tmp_path),
        "unresolved_claims": [],
        "unresolved_questions": [],
        "approval": {"approved": False},
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return tmp_path

def test_valid_candidate(tmp_path):
    assert validator.validate(candidate(tmp_path)) == []

def test_approved_candidate_rejected_before_gate(tmp_path):
    root = candidate(tmp_path)
    approve_candidate(root, "Test User")
    assert any("candidate-ready" in error for error in validator.validate(root))

def test_approved_candidate_validates_at_approved_stage(tmp_path):
    root = candidate(tmp_path)
    approve_candidate(root, "Test User")
    assert validator.validate(root, "approved") == []

def test_claims_file_can_explicitly_contain_no_claims(tmp_path):
    root = candidate(tmp_path)
    (root / "claims.md").write_text("# Claims\n\nNo material claims were detected.\n", encoding="utf-8")
    report_path = root / "generation-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["candidate_digest"] = candidate_digest(root)
    report_path.write_text(json.dumps(report), encoding="utf-8")
    assert validator.validate(root) == []
