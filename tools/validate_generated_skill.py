#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from video_to_skill.exceptions import VideoToSkillError
from video_to_skill.generate.candidate import candidate_digest
from video_to_skill.lifecycle import verify_approved_candidate

REQUIRED = ("SKILL.md", "sources.md", "claims.md", "inconsistencies.md", "generation-report.json")
EVIDENCE = re.compile(r"\b(?:VID|FRM|USR|WEB|INF)-\d{3}\b")

def validate(root: Path, stage: str = "candidate") -> list[str]:
    errors = []
    if not root.is_dir():
        return [f"not a directory: {root}"]
    for name in REQUIRED:
        if not (root / name).is_file():
            errors.append(f"missing required file: {name}")
    report = root / "generation-report.json"
    if report.is_file():
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
            approved = data.get("approval", {}).get("approved")
            state = data.get("state")
            expected_digest = data.get("candidate_digest")
            if not expected_digest or candidate_digest(root) != expected_digest:
                errors.append("candidate digest does not match current files")
            if stage == "candidate" and (approved is not False or state != "candidate-ready"):
                errors.append("candidate validation requires an unapproved candidate-ready report")
            if stage == "approved" and (approved is not True or state != "approved"):
                errors.append("approved validation requires an approved report")
            if stage == "approved" and approved is True and state == "approved":
                try:
                    verify_approved_candidate(root)
                except VideoToSkillError as exc:
                    errors.append(str(exc))
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"invalid generation-report.json: {exc}")
    claims = root / "claims.md"
    if claims.is_file():
        claim_text = claims.read_text(encoding="utf-8")
        if "No material claims were detected." not in claim_text and not EVIDENCE.search(claim_text):
            errors.append("claims.md contains no evidence identifiers")
    return errors

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--stage", choices=("candidate", "approved"), default="candidate")
    args = parser.parse_args()
    errors = validate(args.directory, args.stage)
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    print("Generated skill contract: valid")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
