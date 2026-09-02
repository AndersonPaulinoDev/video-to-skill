import argparse
import json
import sys
from pathlib import Path

from .dependencies import capability_report
from .evals.runner import run_evaluations
from .exceptions import VideoToSkillError
from .extract.visual import inspect_frame, inspect_window
from .generate.candidate import generate_candidate
from .lifecycle import approve_candidate, install_candidate, package_candidate
from .pipeline import analyze
from .workspace import workspace_report

def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="video-to-skill")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Report local extraction capabilities")
    run = commands.add_parser("analyze", help="Extract timestamped evidence from a video")
    run.add_argument("source")
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--frame-interval", type=float, default=60.0)
    run.add_argument("--max-frames", type=int, default=120)
    run.add_argument("--scene-threshold", type=float, default=0.32)
    run.add_argument("--dedup-threshold", type=float, default=6.0)
    run.add_argument("--resume", action="store_true")
    progress = commands.add_parser("progress", help="Report resumable analysis progress")
    progress.add_argument("analysis", type=Path)
    frame = commands.add_parser("inspect-frame", help="Extract one frame for closer inspection")
    frame.add_argument("analysis", type=Path)
    frame.add_argument("timestamp")
    window = commands.add_parser("inspect-window", help="Densely sample a bounded video window")
    window.add_argument("analysis", type=Path)
    window.add_argument("--start", required=True)
    window.add_argument("--end", required=True)
    window.add_argument("--fps", type=float, default=2.0)
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
    evaluate = commands.add_parser("evaluate", help="Run the synthetic end-to-end evaluation suite")
    evaluate.add_argument("--manifest", required=True, type=Path)
    evaluate.add_argument("--output", type=Path)
    evaluate.add_argument("--minimum-score", type=float)
    return root

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            print(json.dumps(capability_report(), indent=2))
            return 0
        if args.command == "analyze":
            if args.frame_interval <= 0 or args.max_frames <= 0 or args.dedup_threshold < 0:
                raise VideoToSkillError("Frame interval and maximum frame count must be positive")
            if not 0 < args.scene_threshold < 1:
                raise VideoToSkillError("Scene threshold must be between 0 and 1")
            result = analyze(
                args.source, args.output, args.frame_interval, args.max_frames, args.resume,
                args.scene_threshold, args.dedup_threshold,
            )
        elif args.command == "progress":
            result = workspace_report(args.analysis)
        elif args.command == "inspect-frame":
            result = inspect_frame(args.analysis, args.timestamp)
        elif args.command == "inspect-window":
            result = inspect_window(args.analysis, args.start, args.end, args.fps)
        elif args.command == "generate":
            result = generate_candidate(
                args.analysis, args.output, args.name, args.description, args.research, args.knowledge
            )
        elif args.command == "approve":
            result = approve_candidate(args.candidate, args.by, args.accept_unresolved)
        elif args.command == "install":
            destination = install_candidate(args.candidate, args.skills_dir)
            result = {"state": "installed", "destination": str(destination)}
        elif args.command == "package":
            package = package_candidate(args.candidate, args.output)
            result = {"state": "packaged", "output": str(package)}
        else:
            result = run_evaluations(args.manifest, args.output, args.minimum_score)
            print(json.dumps(result, indent=2))
            return 0 if result["passed"] else 1
        print(json.dumps(result, indent=2))
        return 0
    except VideoToSkillError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
