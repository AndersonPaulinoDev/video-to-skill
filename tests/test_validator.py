import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "tools" / "validate_generated_skill.py"
SPEC = importlib.util.spec_from_file_location("validator", MODULE_PATH)
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validator)

def candidate(tmp_path: Path) -> Path:
    (tmp_path / "SKILL.md").write_text("---\nname: demo\ndescription: demo\n---\n", encoding="utf-8")
    (tmp_path / "sources.md").write_text("# Sources\n", encoding="utf-8")
    (tmp_path / "claims.md").write_text("# Claims\nSupported by VID-001.\n", encoding="utf-8")
    (tmp_path / "inconsistencies.md").write_text("# Inconsistencies\nNone identified.\n", encoding="utf-8")
    (tmp_path / "generation-report.json").write_text(
        json.dumps({"approval": {"approved": False}}), encoding="utf-8"
    )
    return tmp_path

def test_valid_candidate(tmp_path):
    assert validator.validate(candidate(tmp_path)) == []

def test_approved_candidate_rejected_before_gate(tmp_path):
    root = candidate(tmp_path)
    (root / "generation-report.json").write_text(
        json.dumps({"approval": {"approved": True}}), encoding="utf-8"
    )
    assert any("unapproved" in error for error in validator.validate(root))

