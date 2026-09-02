import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .exceptions import VideoToSkillError
from .generate.candidate import candidate_digest
from .provenance import write_json

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _key_path() -> Path:
    configured = os.environ.get("VIDEO_TO_SKILL_APPROVAL_KEY_FILE")
    return Path(configured).expanduser() if configured else Path.home() / ".config/video-to-skill/approval.key"


def _approval_key(create: bool) -> bytes:
    path = _key_path()
    if path.is_symlink():
        raise VideoToSkillError("Approval key cannot be a symbolic link")
    if not path.exists():
        if not create:
            raise VideoToSkillError("Approval key is unavailable; approval cannot be verified")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(secrets.token_bytes(32))
        path.chmod(0o600)
    key = path.read_bytes()
    if len(key) < 32:
        raise VideoToSkillError("Approval key is invalid")
    return key


def _approval_payload(report: dict) -> bytes:
    payload = json.loads(json.dumps(report))
    payload.setdefault("approval", {})["signature"] = None
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _sign(report: dict, create_key: bool) -> str:
    return hmac.new(_approval_key(create_key), _approval_payload(report), hashlib.sha256).hexdigest()


def _validate_name(name: object) -> str:
    if not isinstance(name, str) or len(name) > 64 or not _SLUG.fullmatch(name):
        raise VideoToSkillError("Generation report contains an invalid skill name")
    return name


def _approval_receipt(report: dict) -> str:
    approval = report["approval"]
    return (
        "# Approval receipt\n\n"
        f"- Approved by: {approval['approved_by']}\n"
        f"- Approved at: {approval['approved_at']}\n"
        f"- Candidate digest: `{report['candidate_digest']}`\n"
        f"- Signature: `{approval['signature']}`\n"
    )


def _load_report(candidate: Path) -> dict:
    if candidate.is_symlink():
        raise VideoToSkillError("Candidate directory cannot be a symbolic link")
    if any(path.is_symlink() for path in candidate.rglob("*")):
        raise VideoToSkillError("Candidate cannot contain symbolic links")
    path = candidate / "generation-report.json"
    if not path.is_file():
        raise VideoToSkillError("Candidate is missing generation-report.json")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VideoToSkillError(f"Invalid generation report: {exc}") from exc
    if report.get("state") not in {"candidate-ready", "approved"}:
        raise VideoToSkillError("Candidate has an invalid lifecycle state")
    _validate_name(report.get("name"))
    expected = report.get("candidate_digest")
    actual = candidate_digest(candidate)
    if not expected or actual != expected:
        raise VideoToSkillError("Candidate contents changed after generation; regenerate before approval")
    return report


def approve_candidate(candidate: Path, approved_by: str, accept_unresolved: bool = False) -> dict:
    report = _load_report(candidate)
    if report.get("state") == "approved":
        raise VideoToSkillError("Candidate is already approved")
    unresolved = bool(
        report.get("unresolved_claims")
        or report.get("unresolved_questions")
        or report.get("unresolved_sources")
    )
    if unresolved and not accept_unresolved:
        raise VideoToSkillError("Candidate has unresolved items; review them or pass --accept-unresolved")
    approved_by = approved_by.strip()
    if not approved_by:
        raise VideoToSkillError("Approver name cannot be empty")
    report["state"] = "approved"
    report["approval"] = {
        "approved": True,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "approved_by": approved_by,
        "accepted_unresolved": bool(unresolved and accept_unresolved),
        "approved_digest": report["candidate_digest"],
        "signature": None,
    }
    if "APPROVAL.md" not in report.get("files", []):
        report.setdefault("files", []).append("APPROVAL.md")
        report["files"].sort()
    report["approval"]["signature"] = _sign(report, create_key=True)
    write_json(candidate / "generation-report.json", report)
    (candidate / "APPROVAL.md").write_text(_approval_receipt(report), encoding="utf-8")
    return report


def _require_approved(candidate: Path) -> dict:
    report = _load_report(candidate)
    approval = report.get("approval", {})
    if report.get("state") != "approved" or approval.get("approved") is not True:
        raise VideoToSkillError("Candidate is not approved")
    if approval.get("approved_digest") != report.get("candidate_digest"):
        raise VideoToSkillError("Approved digest does not match the candidate")
    signature = approval.get("signature")
    if not isinstance(signature, str) or not hmac.compare_digest(signature, _sign(report, create_key=False)):
        raise VideoToSkillError("Approval signature is invalid")
    receipt = candidate / "APPROVAL.md"
    if not receipt.is_file() or receipt.read_text(encoding="utf-8") != _approval_receipt(report):
        raise VideoToSkillError("Approval receipt is missing or invalid")
    return report


def verify_approved_candidate(candidate: Path) -> dict:
    return _require_approved(candidate)


def install_candidate(candidate: Path, skills_dir: Path) -> Path:
    report = _require_approved(candidate)
    if skills_dir.is_symlink():
        raise VideoToSkillError("Skills directory cannot be a symbolic link")
    skills_dir.mkdir(parents=True, exist_ok=True)
    skills_root = skills_dir.resolve()
    destination = (skills_root / _validate_name(report["name"])).resolve()
    if destination.parent != skills_root:
        raise VideoToSkillError("Installation destination escapes the skills directory")
    if destination.exists():
        raise VideoToSkillError(f"Installation destination already exists: {destination}")
    shutil.copytree(candidate, destination)
    installed = _load_report(destination)
    if installed["candidate_digest"] != report["candidate_digest"]:
        shutil.rmtree(destination)
        raise VideoToSkillError("Installed copy failed integrity verification")
    return destination


def package_candidate(candidate: Path, output: Path) -> Path:
    report = _require_approved(candidate)
    if output.exists():
        raise VideoToSkillError(f"Package output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(item for item in candidate.rglob("*") if item.is_file()):
            archive.write(path, f"{report['name']}/{path.relative_to(candidate).as_posix()}")
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        if not names or any(name.startswith("/") or ".." in Path(name).parts for name in names):
            output.unlink(missing_ok=True)
            raise VideoToSkillError("Package verification failed")
    return output
