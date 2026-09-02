import json
from datetime import datetime, timezone
from pathlib import Path

from .analyze.claims import candidate_claims
from .exceptions import VideoToSkillError
from .extract.media import extract_frames, probe_media
from .extract.ocr import ocr_frames
from .extract.subtitles import find_subtitle, parse_subtitle
from .extract.transcript import transcribe
from .generate.preview import build_preview
from .ingest.remote import acquire_url
from .ingest.source import resolve_source
from .provenance import sha256_file, write_json
from .workspace import Workspace


def _read_json(path: Path) -> dict | list:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VideoToSkillError(f"Invalid resumable artifact {path}: {exc}") from exc


def _read_jsonl(path: Path) -> list[dict]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as exc:
        raise VideoToSkillError(f"Invalid resumable transcript {path}: {exc}") from exc


def _media_from_detail(output: Path, detail: dict) -> Path:
    value = Path(detail["working_media"])
    media = value if value.is_absolute() else output / value
    if not media.is_file() or sha256_file(media) != detail.get("media_sha256"):
        raise VideoToSkillError("Previously acquired media is missing or changed; start a new workspace")
    return media


def analyze(source_value: str, output: Path, frame_interval: float = 60.0,
            max_frames: int = 120, resume: bool = False,
            scene_threshold: float = 0.32, dedup_threshold: float = 6.0) -> dict:
    if not resume and output.exists() and any(output.iterdir()):
        raise VideoToSkillError(f"Output directory is not empty: {output}")
    configuration = {
        "frame_interval_seconds": frame_interval,
        "max_frames": max_frames,
        "scene_threshold": scene_threshold,
        "dedup_threshold": dedup_threshold,
    }
    workspace = Workspace(output)
    workspace.initialize(source_value, configuration, resume)

    source = resolve_source(source_value)
    if workspace.is_complete("source"):
        source_detail = workspace.detail("source")
        media = _media_from_detail(output, source_detail)
        if source.kind == "file" and source.local_path.resolve() != media.resolve():
            raise VideoToSkillError("Resume source resolves to a different local file")
        metadata = source_detail.get("metadata", {})
    else:
        workspace.running("source")
        try:
            metadata = {}
            if source.kind == "url":
                media, metadata = acquire_url(source.value, output)
            else:
                media = source.local_path
            if media is None:
                raise VideoToSkillError("No local media was resolved")
            working_media = (
                str(media.relative_to(output)) if source.kind == "url" else str(media.resolve())
            )
            source_detail = {
                "source_kind": source.kind,
                "source_display": source.value,
                "working_media": working_media,
                "media_sha256": sha256_file(media),
                "metadata": metadata,
            }
            workspace.complete("source", source_detail)
        except Exception as exc:
            workspace.fail("source", str(exc))
            raise

    if workspace.is_complete("probe"):
        probe = _read_json(output / "probe.json")
    else:
        workspace.running("probe")
        try:
            probe = probe_media(media)
            write_json(output / "probe.json", probe)
            workspace.complete("probe", {"duration_seconds": probe["duration_seconds"]})
        except Exception as exc:
            workspace.fail("probe", str(exc))
            raise

    if workspace.is_complete("transcript"):
        cues = _read_jsonl(output / "transcript.jsonl")
        transcript_detail = workspace.detail("transcript")
        subtitle_value = transcript_detail.get("subtitle")
        subtitle = Path(subtitle_value) if subtitle_value else None
        transcript_method = transcript_detail.get("method")
    else:
        workspace.running("transcript")
        try:
            subtitle = find_subtitle(media)
            transcript_method = "subtitle" if subtitle else None
            if subtitle:
                cues = parse_subtitle(subtitle)
            else:
                try:
                    cues, transcript_method = transcribe(media, output)
                except VideoToSkillError:
                    cues = []
            (output / "transcript.jsonl").write_text(
                "".join(json.dumps(cue, ensure_ascii=False) + "\n" for cue in cues),
                encoding="utf-8",
            )
            workspace.complete("transcript", {
                "cue_count": len(cues),
                "subtitle": str(subtitle) if subtitle else None,
                "method": transcript_method,
            })
        except Exception as exc:
            workspace.fail("transcript", str(exc))
            raise

    if workspace.is_complete("frames"):
        frames = _read_json(output / "frames.json")
    else:
        workspace.running("frames")
        try:
            frames = extract_frames(
                media, output / "frames", probe["duration_seconds"], frame_interval, max_frames,
                scene_threshold, dedup_threshold,
            )
            for record in frames:
                record["sha256"] = sha256_file(Path(record["path"]))
                record["path"] = str(Path(record["path"]).relative_to(output))
            write_json(output / "frames.json", frames)
            workspace.complete("frames", {
                "frame_count": len(frames),
                "periodic": sum(item.get("selection") == "periodic" for item in frames),
                "scene_changes": sum(item.get("selection") == "scene-change" for item in frames),
            })
        except Exception as exc:
            workspace.fail("frames", str(exc))
            raise

    if workspace.is_complete("ocr"):
        ocr = _read_json(output / "ocr.json")
    else:
        workspace.running("ocr")
        try:
            ocr = ocr_frames(frames, output)
            write_json(output / "ocr.json", ocr)
            workspace.complete("ocr", {"record_count": len(ocr)})
        except Exception as exc:
            workspace.fail("ocr", str(exc))
            raise

    if workspace.is_complete("finalize"):
        return _read_json(output / "preview.json")

    workspace.running("finalize")
    try:
        gaps = []
        if not cues:
            gaps.append(
                "No subtitle or local transcription evidence was available; semantic generation must stop."
            )
        manifest = {
            "schema_version": 2,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_kind": source.kind,
            "source_display": source.value,
            "working_media": source_detail["working_media"],
            "media_sha256": source_detail["media_sha256"],
            "metadata": metadata,
            "probe": probe,
            "processing": {
                "subtitle": str(subtitle) if subtitle else None,
                "transcript_method": transcript_method,
                "ocr_method": "tesseract" if ocr else None,
                **configuration,
                "resumable_workspace": True,
            },
            "unresolved_gaps": gaps,
            "status": "partial" if gaps else "extracted",
        }
        claims = candidate_claims(cues)
        write_json(output / "claims.json", claims)
        write_json(output / "manifest.json", manifest)
        preview = build_preview(manifest, claims, cues, frames)
        write_json(output / "preview.json", preview)
        workspace.complete("finalize", {"status": manifest["status"]})
        return preview
    except Exception as exc:
        workspace.fail("finalize", str(exc))
        raise
