import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from importlib.util import find_spec
from pathlib import Path
from urllib.parse import urlparse

from .exceptions import VideoToSkillError
from .pipeline import analyze
from .provenance import write_json


_SOURCE_ID = re.compile(r"^SRC-\d{3}$")


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VideoToSkillError(f"Invalid course inventory {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise VideoToSkillError("Course inventory must be a JSON object")
    return payload


def _validate_inventory(payload: dict) -> dict:
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        raise VideoToSkillError("Course inventory must contain at least one source")
    clean = []
    seen = set()
    for index, item in enumerate(sources, 1):
        if not isinstance(item, dict):
            raise VideoToSkillError("Every course source must be an object")
        source_id = str(item.get("id") or f"SRC-{index:03d}")
        source = str(item.get("source", "")).strip()
        if not _SOURCE_ID.fullmatch(source_id) or source_id in seen:
            raise VideoToSkillError(f"Invalid or duplicate course source id: {source_id}")
        if not source:
            raise VideoToSkillError(f"Course source {source_id} is empty")
        seen.add(source_id)
        clean.append({
            "id": source_id,
            "source": source,
            "title": str(item.get("title") or source_id),
            "position": index,
        })
    return {
        "schema_version": 1,
        "title": str(payload.get("title") or "Untitled course"),
        "sources": clean,
    }


def inventory_course(source: str, output: Path) -> dict:
    if output.exists():
        raise VideoToSkillError(f"Inventory output already exists: {output}")
    local = Path(source).expanduser()
    if local.is_file():
        local = local.resolve()
        inventory = _validate_inventory(_read_json(local))
        for item in inventory["sources"]:
            parsed_item = urlparse(item["source"])
            if not parsed_item.scheme:
                item["source"] = str((local.parent / item["source"]).resolve())
    else:
        parsed = urlparse(source)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
            raise VideoToSkillError("Course source must be an inventory JSON file or public HTTP(S) URL")
        if shutil.which("yt-dlp"):
            runner = ["yt-dlp"]
        elif find_spec("yt_dlp") is not None:
            runner = [sys.executable, "-m", "yt_dlp"]
        else:
            raise VideoToSkillError("Playlist inventory requires yt-dlp")
        command = runner + ["--flat-playlist", "--dump-single-json", "--no-warnings", source]
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            raw = json.loads(result.stdout)
        except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
            raise VideoToSkillError("Could not inventory the public playlist or course URL") from exc
        entries = raw.get("entries", [])
        inventory = _validate_inventory({
            "title": raw.get("title") or "Untitled course",
            "sources": [
                {
                    "id": f"SRC-{index:03d}",
                    "source": entry.get("webpage_url") or entry.get("url"),
                    "title": entry.get("title") or f"Source {index}",
                }
                for index, entry in enumerate(entries, 1)
                if isinstance(entry, dict) and (entry.get("webpage_url") or entry.get("url"))
            ],
        })
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, inventory)
    return inventory


def _load_analysis(root: Path) -> tuple[dict, list, list, list, list]:
    required = ("manifest.json", "claims.json", "frames.json", "ocr.json", "transcript.jsonl")
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise VideoToSkillError(f"Analysis {root} is missing: {', '.join(missing)}")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    claims = json.loads((root / "claims.json").read_text(encoding="utf-8"))
    frames = json.loads((root / "frames.json").read_text(encoding="utf-8"))
    ocr = json.loads((root / "ocr.json").read_text(encoding="utf-8"))
    cues = [json.loads(line) for line in (root / "transcript.jsonl").read_text(encoding="utf-8").splitlines() if line]
    if manifest.get("status") != "extracted":
        raise VideoToSkillError(f"Analysis is not complete: {root}")
    return manifest, claims, frames, ocr, cues


def merge_analyses(inputs: list[Path], output: Path, title: str = "Merged video sources",
                   source_descriptors: list[dict] | None = None) -> dict:
    if len(inputs) < 1:
        raise VideoToSkillError("At least one complete analysis is required")
    if output.is_symlink():
        raise VideoToSkillError("Merge output cannot be a symbolic link")
    if output.exists() and any(output.iterdir()):
        raise VideoToSkillError(f"Merge output is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    frames_root = output / "frames"
    frames_root.mkdir()
    merged_cues, merged_frames, merged_ocr, merged_claims, sources = [], [], [], [], []
    claim_by_text = {}
    cue_number = frame_number = claim_number = 0
    for source_number, analysis in enumerate(inputs, 1):
        if analysis.is_symlink():
            raise VideoToSkillError("Analysis input cannot be a symbolic link")
        analysis = analysis.resolve()
        manifest, claims, frames, ocr, cues = _load_analysis(analysis)
        descriptor = source_descriptors[source_number - 1] if source_descriptors else {}
        source_id = str(descriptor.get("id") or f"SRC-{source_number:03d}")
        if not _SOURCE_ID.fullmatch(source_id) or any(item["id"] == source_id for item in sources):
            raise VideoToSkillError(f"Invalid or duplicate merged source id: {source_id}")
        sources.append({
            "id": source_id,
            "display": str(descriptor.get("title") or manifest["source_display"]),
            "sha256": manifest["media_sha256"],
            "duration_seconds": manifest.get("probe", {}).get("duration_seconds"),
        })
        cue_map = {}
        for cue in cues:
            cue_number += 1
            new_id = f"VID-{cue_number:03d}"
            cue_map[cue["id"]] = new_id
            merged_cues.append({**cue, "id": new_id, "source_id": source_id})
        frame_map = {}
        for frame in frames:
            frame_number += 1
            new_id = f"FRM-{frame_number:03d}"
            frame_map[frame["id"]] = new_id
            raw_source_path = analysis / frame["path"]
            source_path = raw_source_path.resolve()
            if analysis not in source_path.parents or raw_source_path.is_symlink():
                raise VideoToSkillError("Frame evidence escapes its analysis directory")
            suffix = source_path.suffix.lower() or ".jpg"
            target = frames_root / f"{new_id.lower()}{suffix}"
            if not source_path.is_file():
                raise VideoToSkillError(f"Frame evidence is missing: {source_path}")
            shutil.copy2(source_path, target)
            merged_frames.append({
                **frame, "id": new_id, "source_id": source_id,
                "path": str(target.relative_to(output)),
            })
        for item in ocr:
            if item.get("id") in frame_map:
                merged_ocr.append({**item, "id": frame_map[item["id"]], "source_id": source_id})
        evidence_map = {**cue_map, **frame_map}
        for claim in claims:
            text_key = " ".join(str(claim.get("text", "")).casefold().split())
            mapped_evidence = [evidence_map[item] for item in claim.get("evidence", []) if item in evidence_map]
            if text_key in claim_by_text:
                existing = claim_by_text[text_key]
                existing["evidence"] = list(dict.fromkeys(existing["evidence"] + mapped_evidence))
                existing["source_ids"] = list(dict.fromkeys(existing["source_ids"] + [source_id]))
                continue
            claim_number += 1
            merged = {
                **claim,
                "id": f"CLM-{claim_number:03d}",
                "evidence": mapped_evidence,
                "source_ids": [source_id],
                "status": "not-researched",
                "confidence": None,
            }
            merged_claims.append(merged)
            claim_by_text[text_key] = merged
    manifest = {
        "schema_version": 3,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_kind": "course" if len(sources) > 1 else "merged",
        "source_display": title,
        "working_media": None,
        "media_sha256": "multi-source",
        "sources": sources,
        "metadata": {"source_count": len(sources)},
        "probe": {"duration_seconds": sum(float(item.get("duration_seconds") or 0) for item in sources)},
        "processing": {"merged_analysis": True},
        "unresolved_gaps": [],
        "status": "extracted",
    }
    (output / "transcript.jsonl").write_text(
        "".join(json.dumps(cue, ensure_ascii=False) + "\n" for cue in merged_cues), encoding="utf-8"
    )
    write_json(output / "frames.json", merged_frames)
    write_json(output / "ocr.json", merged_ocr)
    write_json(output / "claims.json", merged_claims)
    write_json(output / "manifest.json", manifest)
    preview = {
        "state": "analysis-ready",
        "install_or_publish_allowed": False,
        "source": {"kind": manifest["source_kind"], "display": title},
        "processing": manifest["processing"],
        "evidence": {
            "transcript_cues": len(merged_cues), "sampled_frames": len(merged_frames),
            "candidate_claims": len(merged_claims), "source_count": len(sources),
        },
        "research": {"required": True, "completed": False},
        "unresolved_gaps": [],
        "next_action": "Create knowledge.json and research.json, then run the generate command.",
    }
    write_json(output / "preview.json", preview)
    return preview


def analyze_course(inventory_path: Path, output: Path, resume: bool = False,
                   frame_interval: float = 60.0, max_frames: int = 120,
                   scene_threshold: float = 0.32, dedup_threshold: float = 6.0) -> dict:
    inventory = _validate_inventory(_read_json(inventory_path))
    if output.is_symlink():
        raise VideoToSkillError("Course output cannot be a symbolic link")
    if not resume and output.exists() and any(output.iterdir()):
        raise VideoToSkillError(f"Course output is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    analyses_root = output / "analyses"
    analyses_root.mkdir(exist_ok=True)
    results, successful, successful_descriptors = [], [], []
    for item in inventory["sources"]:
        target = analyses_root / item["id"]
        can_resume = resume and (target / "workspace.sqlite3").is_file()
        try:
            source_value = item["source"]
            if not urlparse(source_value).scheme and not Path(source_value).is_absolute():
                source_value = str((inventory_path.resolve().parent / source_value).resolve())
            analyze(
                source_value, target, frame_interval, max_frames, can_resume,
                scene_threshold, dedup_threshold,
            )
            results.append({**item, "status": "complete", "analysis": str(target)})
            successful.append(target)
            successful_descriptors.append(item)
        except (VideoToSkillError, OSError) as exc:
            results.append({**item, "status": "failed", "error": str(exc)})
    if not successful:
        raise VideoToSkillError("No course sources completed successfully")
    merged = output / "merged"
    if merged.exists():
        if merged.is_symlink():
            raise VideoToSkillError("Merged course output cannot be a symbolic link")
        shutil.rmtree(merged)
    merge_analyses(successful, merged, inventory["title"], successful_descriptors)
    report = {
        "schema_version": 1,
        "title": inventory["title"],
        "expected_sources": len(results),
        "completed_sources": len(successful),
        "failed_sources": len(results) - len(successful),
        "complete": len(successful) == len(results),
        "merged_analysis": str(merged),
        "sources": results,
    }
    merged_manifest_path = merged / "manifest.json"
    merged_manifest = json.loads(merged_manifest_path.read_text(encoding="utf-8"))
    merged_manifest["coverage"] = {
        "expected_sources": report["expected_sources"],
        "completed_sources": report["completed_sources"],
        "failed_sources": report["failed_sources"],
        "complete": report["complete"],
        "unresolved_sources": [
            {"id": item["id"], "title": item["title"], "error": item.get("error", "Unavailable")}
            for item in results if item["status"] == "failed"
        ],
    }
    if not report["complete"]:
        merged_manifest["unresolved_gaps"].append(
            f"{report['failed_sources']} of {report['expected_sources']} course sources failed analysis."
        )
    write_json(merged_manifest_path, merged_manifest)
    merged_preview_path = merged / "preview.json"
    merged_preview = json.loads(merged_preview_path.read_text(encoding="utf-8"))
    merged_preview["coverage"] = merged_manifest["coverage"]
    merged_preview["unresolved_gaps"] = merged_manifest["unresolved_gaps"]
    write_json(merged_preview_path, merged_preview)
    write_json(output / "course-report.json", report)
    return report
