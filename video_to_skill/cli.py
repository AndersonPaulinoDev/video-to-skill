import argparse
import json
import sys
from pathlib import Path

from .dependencies import capability_report
from .exceptions import VideoToSkillError
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
    return root

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            print(json.dumps(capability_report(), indent=2))
            return 0
        if args.frame_interval <= 0 or args.max_frames <= 0:
            raise VideoToSkillError("Frame interval and maximum frame count must be positive")
        print(json.dumps(analyze(args.source, args.output, args.frame_interval, args.max_frames), indent=2))
        return 0
    except VideoToSkillError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

