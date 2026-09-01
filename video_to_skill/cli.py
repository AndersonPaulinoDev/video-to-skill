import argparse
import json
import sys
from pathlib import Path

from .dependencies import capability_report
from .exceptions import VideoToSkillError
from .generate.candidate import generate_candidate
from .lifecycle import approve_candidate, install_candidate, package_candidate
from .pipeline import analyze

def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="video-to-skill")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Report local extraction capabilities")
    run = commands.add_parser("analyze", help="Extract timestamped evidence from a video")
    run.add_argument("source")
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--frame-interval", type=float, default=60.0)
    run.add_argument("--max-frames", type=int, default=120)
    generate = commands.add_parser("generate", help="Build a complete candidate skill from analyzed evidence")
    generate.add_argument("analysis", type=Path)
    generate.add_argument("--output", required=True, type=Path)
    generate.add_argument("--name", required=True)
    generate.add_argument("--description", required=True)
    generate.add_argument("--research", type=Path)
    generate.add_argument("--knowledge", type=Path)
    approve = commands.add_parser("approve", help="Record explicit approval for an unchanged candidate")
    approve.add_argument("candidate", type=Path)
    approve.add_argument("--by", required=True)
    approve.add_argument("--accept-unresolved", action="store_true")
    install = commands.add_parser("install", help="Install an approved candidate into a skills directory")
    install.add_argument("candidate", type=Path)
    install.add_argument("--skills-dir", required=True, type=Path)
    package = commands.add_parser("package", help="Create a verified zip from an approved candidate")
    package.add_argument("candidate", type=Path)
    package.add_argument("--output", required=True, type=Path)
    return root

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            print(json.dumps(capability_report(), indent=2))
            return 0
        if args.command == "analyze":
            if args.frame_interval <= 0 or args.max_frames <= 0:
                raise VideoToSkillError("Frame interval and maximum frame count must be positive")
            result = analyze(args.source, args.output, args.frame_interval, args.max_frames)
        elif args.command == "generate":
            result = generate_candidate(
                args.analysis, args.output, args.name, args.description, args.research, args.knowledge
            )
        elif args.command == "approve":
            result = approve_candidate(args.candidate, args.by, args.accept_unresolved)
        elif args.command == "install":
            destination = install_candidate(args.candidate, args.skills_dir)
            result = {"state": "installed", "destination": str(destination)}
        else:
            package = package_candidate(args.candidate, args.output)
            result = {"state": "packaged", "output": str(package)}
        print(json.dumps(result, indent=2))
        return 0
    except VideoToSkillError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
