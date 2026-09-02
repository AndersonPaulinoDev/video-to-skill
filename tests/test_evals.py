import json
import shutil
from pathlib import Path

import pytest

from video_to_skill.evals.runner import run_evaluations
from video_to_skill.exceptions import VideoToSkillError


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is required")
def test_owned_fixture_suite_passes(tmp_path):
    report = run_evaluations(ROOT / "evals/manifest.json", tmp_path / "report.json")

    assert report["passed"] is True
    assert report["score"] == 1.0
    assert report["case_count"] == 4
    assert all(case["passed"] for case in report["cases"])
    assert json.loads((tmp_path / "report.json").read_text())["passed"] is True


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is required")
def test_wrong_expectation_fails_closed(tmp_path):
    fixture = tmp_path / "fixture"
    shutil.copytree(ROOT / "evals/fixtures/approval-tutorial", fixture)
    expected_path = fixture / "expected.json"
    expected = json.loads(expected_path.read_text())
    expected["knowledge_phrases"].append("phrase that cannot exist")
    expected_path.write_text(json.dumps(expected), encoding="utf-8")
    manifest = {
        "minimum_score": 0.5,
        "cases": [{
            "id": "negative",
            "fixture": "fixture",
            "name": "negative-evaluation",
            "description": "Use for testing evaluator failure behavior.",
        }],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = run_evaluations(manifest_path)

    assert report["passed"] is False
    assert report["cases"][0]["passed"] is False
    assert "one or more expected knowledge phrases were missing" in report["cases"][0]["failures"]


def test_manifest_path_escape_is_reported_as_failure(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({
        "cases": [{
            "id": "escape",
            "fixture": "../outside",
            "name": "escape",
            "description": "Must never be loaded.",
        }]
    }), encoding="utf-8")

    report = run_evaluations(manifest_path)

    assert report["passed"] is False
    assert "escapes manifest directory" in report["cases"][0]["failures"][0]


def test_invalid_global_threshold_is_rejected():
    with pytest.raises(VideoToSkillError, match="between 0 and 1"):
        run_evaluations(ROOT / "evals/manifest.json", minimum_score=1.1)


def test_case_id_path_escape_is_rejected(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({
        "cases": [{
            "id": "../escape",
            "fixture": "unused",
            "name": "escape",
            "description": "Must never be created.",
        }]
    }), encoding="utf-8")

    report = run_evaluations(manifest_path)

    assert report["passed"] is False
    assert "lowercase letters" in report["cases"][0]["failures"][0]
    assert not (tmp_path.parent / "escape").exists()


def test_fixture_resource_limits_fail_closed(tmp_path):
    fixture = tmp_path / "fixture"
    shutil.copytree(ROOT / "evals/fixtures/approval-tutorial", fixture)
    spec_path = fixture / "video-spec.json"
    spec = json.loads(spec_path.read_text())
    spec["size"] = "9999x9999"
    spec["max_frames"] = 1_000_000
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({
        "cases": [{
            "id": "resource-limit",
            "fixture": "fixture",
            "name": "resource-limit",
            "description": "Must fail before generating media.",
        }]
    }), encoding="utf-8")

    report = run_evaluations(manifest_path)

    assert report["passed"] is False
    assert "must not exceed 1920x1080" in report["cases"][0]["failures"][0]
