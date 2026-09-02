import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ..exceptions import VideoToSkillError
from ..generate.candidate import generate_candidate
from ..pipeline import analyze
from ..provenance import write_json

_REQUIRED_FILES = {
    "PREVIEW.md",
    "SKILL.md",
    "claims.md",
    "generation-report.json",
    "inconsistencies.md",
    "references/knowledge.md",
    "sources.md",
}
_WEIGHTS = {
    "analysis": 0.15,
    "structure": 0.15,
    "claim_status": 0.15,
    "evidence": 0.15,
    "knowledge": 0.15,
    "conflicts": 0.15,
    "approval_gate": 0.10,
}
_CASE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_SIZE = re.compile(r"^([1-9][0-9]{1,3})x([1-9][0-9]{1,3})$")
_COLOR = re.compile(r"^(?:[A-Za-z]{1,24}|0x[0-9A-Fa-f]{6})$")


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VideoToSkillError(f"Invalid evaluation JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise VideoToSkillError(f"Evaluation JSON must be an object: {path}")
    return payload


def _fixture_path(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    if path != root and root not in path.parents:
        raise VideoToSkillError(f"Evaluation path escapes manifest directory: {value}")
    return path


def _build_video(fixture: Path, destination: Path) -> tuple[Path, dict]:
    spec = _read_json(fixture / "video-spec.json")
    if not shutil.which("ffmpeg"):
        raise VideoToSkillError("Evaluation video generation requires ffmpeg")
    duration = float(spec.get("duration_seconds", 2))
    if duration <= 0 or duration > 60:
        raise VideoToSkillError("Synthetic evaluation duration must be between 0 and 60 seconds")
    size = str(spec.get("size", "320x180"))
    color = str(spec.get("color", "blue"))
    size_match = _SIZE.fullmatch(size)
    if not size_match:
        raise VideoToSkillError("Synthetic evaluation size must use WIDTHxHEIGHT")
    width, height = (int(value) for value in size_match.groups())
    if width > 1920 or height > 1080 or width * height > 2_073_600:
        raise VideoToSkillError("Synthetic evaluation size must not exceed 1920x1080")
    if not _COLOR.fullmatch(color):
        raise VideoToSkillError("Synthetic evaluation color must be a name or 0xRRGGBB value")
    interval = float(spec.get("frame_interval_seconds", 1))
    maximum = int(spec.get("max_frames", 10))
    if not 0 < interval <= 60:
        raise VideoToSkillError("Synthetic frame interval must be between 0 and 60 seconds")
    if not 0 < maximum <= 300:
        raise VideoToSkillError("Synthetic maximum frames must be between 1 and 300")
    video = destination / "source.mp4"
    command = [
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
        f"color=c={color}:s={size}:d={duration}", "-c:v", "libx264", str(video),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise VideoToSkillError((exc.stderr or "Synthetic video generation failed").strip()) from exc
    subtitle_name = spec.get("subtitle")
    if subtitle_name:
        subtitle = _fixture_path(fixture, subtitle_name)
        if not subtitle.is_file():
            raise VideoToSkillError(f"Synthetic subtitle not found: {subtitle}")
        shutil.copy2(subtitle, destination / f"source{subtitle.suffix.lower()}")
    return video, spec


def _ratio(found: int, expected: int) -> float:
    return 1.0 if expected == 0 else min(1.0, found / expected)


def _score_case(candidate: Path, preview: dict, expected: dict) -> tuple[dict, list[str]]:
    failures = []
    actual_files = {path.relative_to(candidate).as_posix() for path in candidate.rglob("*") if path.is_file()}
    missing_files = sorted(_REQUIRED_FILES - actual_files)
    structure = _ratio(len(_REQUIRED_FILES) - len(missing_files), len(_REQUIRED_FILES))
    if missing_files:
        failures.append(f"missing files: {', '.join(missing_files)}")

    analysis_expected = expected.get("analysis", {})
    analysis_checks = {
        "transcript_cues": preview.get("evidence", {}).get("transcript_cues", 0),
        "candidate_claims": preview.get("evidence", {}).get("candidate_claims", 0),
    }
    analysis_parts = []
    for key, wanted in analysis_expected.items():
        actual = analysis_checks.get(key, preview.get("evidence", {}).get(key, 0))
        if key == "minimum_frames":
            actual = preview.get("evidence", {}).get("sampled_frames", 0)
            passed = actual >= wanted
        else:
            passed = actual == wanted
        analysis_parts.append(1.0 if passed else 0.0)
        if not passed:
            failures.append(f"analysis {key}: expected {wanted}, got {actual}")
    analysis_score = sum(analysis_parts) / len(analysis_parts) if analysis_parts else 1.0

    claims_text = (candidate / "claims.md").read_text(encoding="utf-8")
    expected_statuses = expected.get("claim_statuses", {})
    matched_statuses = sum(
        f"## {claim_id}: {status}" in claims_text for claim_id, status in expected_statuses.items()
    )
    claim_score = _ratio(matched_statuses, len(expected_statuses))
    if matched_statuses != len(expected_statuses):
        failures.append("one or more claim statuses did not match")

    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in candidate.rglob("*")
        if path.is_file() and path.suffix in {".md", ".json"}
    )
    expected_evidence = expected.get("evidence_ids", [])
    found_evidence = sum(evidence_id in combined for evidence_id in expected_evidence)
    evidence_score = _ratio(found_evidence, len(expected_evidence))
    if found_evidence != len(expected_evidence):
        failures.append("one or more expected evidence identifiers were missing")

    knowledge_text = (candidate / "references/knowledge.md").read_text(encoding="utf-8").casefold()
    knowledge_phrases = [str(value).casefold() for value in expected.get("knowledge_phrases", [])]
    found_knowledge = sum(value in knowledge_text for value in knowledge_phrases)
    knowledge_score = _ratio(found_knowledge, len(knowledge_phrases))
    if found_knowledge != len(knowledge_phrases):
        failures.append("one or more expected knowledge phrases were missing")

    conflicts_text = (candidate / "inconsistencies.md").read_text(encoding="utf-8").casefold()
    conflict_phrases = [str(value).casefold() for value in expected.get("conflict_phrases", [])]
    found_conflicts = sum(value in conflicts_text for value in conflict_phrases)
    conflict_score = _ratio(found_conflicts, len(conflict_phrases))
    if found_conflicts != len(conflict_phrases):
        failures.append("one or more expected conflict phrases were missing")

    report = _read_json(candidate / "generation-report.json")
    approval_score = float(
        report.get("state") == "candidate-ready"
        and report.get("approval", {}).get("approved") is False
        and preview.get("install_or_publish_allowed") is False
    )
    if approval_score != 1:
        failures.append("candidate approval gate was not closed")

    metrics = {
        "analysis": analysis_score,
        "structure": structure,
        "claim_status": claim_score,
        "evidence": evidence_score,
        "knowledge": knowledge_score,
        "conflicts": conflict_score,
        "approval_gate": approval_score,
    }
    score = sum(metrics[name] * _WEIGHTS[name] for name in _WEIGHTS)
    metrics["overall"] = round(score, 6)
    return metrics, failures


def _run_case(manifest_root: Path, case: dict, workspace: Path) -> dict:
    case_id = str(case.get("id", "")).strip()
    if not _CASE_ID.fullmatch(case_id):
        raise VideoToSkillError(
            "Evaluation case id must contain only lowercase letters, numbers, and hyphens"
        )
    fixture = _fixture_path(manifest_root, str(case.get("fixture", "")))
    expected = _read_json(fixture / "expected.json")
    minimum = float(expected.get("minimum_score", case.get("minimum_score", 0.9)))
    if not 0 <= minimum <= 1:
        raise VideoToSkillError("Evaluation case minimum score must be between 0 and 1")
    case_root = workspace / case_id
    case_root.mkdir()
    video, spec = _build_video(fixture, case_root)
    analysis_dir = case_root / "analysis"
    preview = analyze(
        str(video),
        analysis_dir,
        float(spec.get("frame_interval_seconds", 1)),
        int(spec.get("max_frames", 10)),
    )
    candidate = case_root / "candidate"
    generate_candidate(
        analysis_dir,
        candidate,
        str(case["name"]),
        str(case["description"]),
        fixture / "research.json" if (fixture / "research.json").is_file() else None,
        fixture / "knowledge.json" if (fixture / "knowledge.json").is_file() else None,
    )
    metrics, failures = _score_case(candidate, preview, expected)
    return {
        "id": case_id,
        "score": metrics["overall"],
        "minimum_score": minimum,
        "passed": metrics["overall"] >= minimum and not failures,
        "metrics": metrics,
        "failures": failures,
    }


def run_evaluations(manifest_path: Path, output: Path | None = None,
                    minimum_score: float | None = None) -> dict:
    manifest_path = manifest_path.resolve()
    manifest = _read_json(manifest_path)
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise VideoToSkillError("Evaluation manifest must contain at least one case")
    default_minimum = float(manifest.get("minimum_score", 0.9))
    threshold = default_minimum if minimum_score is None else minimum_score
    if not 0 <= threshold <= 1:
        raise VideoToSkillError("Evaluation minimum score must be between 0 and 1")
    results = []
    with tempfile.TemporaryDirectory(prefix="video-to-skill-evals-") as temporary:
        workspace = Path(temporary)
        seen_ids = set()
        for case in cases:
            if not isinstance(case, dict):
                results.append({
                    "id": "unknown",
                    "score": 0.0,
                    "minimum_score": threshold,
                    "passed": False,
                    "metrics": {},
                    "failures": ["Evaluation case must be an object"],
                })
                continue
            case_id = str(case.get("id", "")).strip()
            if case_id in seen_ids:
                results.append({
                    "id": case_id,
                    "score": 0.0,
                    "minimum_score": threshold,
                    "passed": False,
                    "metrics": {},
                    "failures": [f"Duplicate evaluation case id: {case_id}"],
                })
                continue
            seen_ids.add(case_id)
            try:
                results.append(_run_case(manifest_path.parent, case, workspace))
            except (VideoToSkillError, KeyError, TypeError, ValueError) as exc:
                results.append({
                    "id": str(case.get("id", "unknown")),
                    "score": 0.0,
                    "minimum_score": threshold,
                    "passed": False,
                    "metrics": {},
                    "failures": [str(exc)],
                })
    overall = sum(result["score"] for result in results) / len(results)
    report = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "manifest": str(manifest_path),
        "case_count": len(results),
        "score": round(overall, 6),
        "minimum_score": threshold,
        "passed": overall >= threshold and all(result["passed"] for result in results),
        "weights": _WEIGHTS,
        "cases": results,
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        write_json(output, report)
    return report
