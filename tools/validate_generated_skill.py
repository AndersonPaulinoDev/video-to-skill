#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED = ("SKILL.md", "sources.md", "claims.md", "inconsistencies.md", "generation-report.json")
EVIDENCE = re.compile(r"\b(?:VID|FRM|USR|WEB|INF)-\d{3}\b")

def validate(root: Path) -> list[str]:
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
            if data.get("approval", {}).get("approved") is not False:
                errors.append("generation report must remain unapproved before user approval")
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"invalid generation-report.json: {exc}")
    claims = root / "claims.md"
    if claims.is_file() and not EVIDENCE.search(claims.read_text(encoding="utf-8")):
        errors.append("claims.md contains no evidence identifiers")
    return errors

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    errors = validate(parser.parse_args().directory)
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    print("Generated skill contract: valid")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
