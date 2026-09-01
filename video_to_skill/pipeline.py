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

def analyze(source_value: str, output: Path, frame_interval: float = 60.0, max_frames: int = 120) -> dict:
    if output.exists() and any(output.iterdir()):
        raise VideoToSkillError(f"Output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    source = resolve_source(source_value)
    metadata = {}
    if source.kind == "url":
        media, metadata = acquire_url(source.value, output)
    else:
        media = source.local_path
    if media is None:
        raise VideoToSkillError("No local media was resolved")
    probe = probe_media(media)
    subtitle = find_subtitle(media)
    transcript_method = "subtitle" if subtitle else None
    if subtitle:
        cues = parse_subtitle(subtitle)
    else:
        try:
            cues, transcript_method = transcribe(media, output)
        except VideoToSkillError:
            cues = []
    frames = extract_frames(media, output / "frames", probe["duration_seconds"], frame_interval, max_frames)
    for record in frames:
        record["sha256"] = sha256_file(Path(record["path"]))
        record["path"] = str(Path(record["path"]).relative_to(output))
    ocr = ocr_frames(frames, output)
    (output / "transcript.jsonl").write_text(
        "".join(json.dumps(cue, ensure_ascii=False) + "\n" for cue in cues), encoding="utf-8"
    )
    gaps = []
    if not cues:
        gaps.append("No subtitle or local transcription evidence was available; semantic generation must stop.")
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_kind": source.kind,
        "source_display": source.value,
        "working_media": str(media.relative_to(output)) if source.kind == "url" else str(media),
        "media_sha256": sha256_file(media),
        "metadata": metadata,
        "probe": probe,
        "processing": {"subtitle": str(subtitle) if subtitle else None,
                       "transcript_method": transcript_method,
                       "ocr_method": "tesseract" if ocr else None,
                       "frame_interval_seconds": frame_interval, "max_frames": max_frames},
        "unresolved_gaps": gaps,
        "status": "partial" if gaps else "extracted",
    }
    claims = candidate_claims(cues)
    write_json(output / "claims.json", claims)
    write_json(output / "frames.json", frames)
    write_json(output / "ocr.json", ocr)
    write_json(output / "manifest.json", manifest)
    preview = build_preview(manifest, claims, cues, frames)
    write_json(output / "preview.json", preview)
    return preview
