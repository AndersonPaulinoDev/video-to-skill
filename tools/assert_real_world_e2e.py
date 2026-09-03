import hashlib
import json
import sys
import zipfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail(message: str) -> None:
    raise SystemExit(f"REAL-WORLD E2E FAILED: {message}")


def main() -> None:
    if len(sys.argv) != 5:
        fail("usage: assert_real_world_e2e.py <analysis> <candidate> <installed> <zip>")

    analysis = Path(sys.argv[1])
    candidate = Path(sys.argv[2])
    installed = Path(sys.argv[3])
    archive = Path(sys.argv[4])

    manifest = json.loads((analysis / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("source_kind") != "url":
        fail(f"expected URL source, got {manifest.get('source_kind')!r}")
    if manifest.get("status") != "extracted":
        fail(f"analysis is not complete: {manifest.get('status')!r}; gaps={manifest.get('unresolved_gaps')}")

    media = analysis / manifest["working_media"]
    if not media.is_file() or media.stat().st_size < 1_000_000:
        fail("real downloaded media is missing or implausibly small")
    if sha256(media) != manifest.get("media_sha256"):
        fail("downloaded media hash does not match manifest provenance")

    transcript = [
        json.loads(line)
        for line in (analysis / "transcript.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not transcript:
        fail("no real transcript cues were produced")
    transcript_method = manifest.get("processing", {}).get("transcript_method")
    if transcript_method not in {"subtitle", "faster-whisper", "whisper"}:
        fail(f"unexpected transcript method: {transcript_method!r}")
    if not any(str(cue.get("text", "")).strip() for cue in transcript):
        fail("transcript cues contain no text")

    frames = json.loads((analysis / "frames.json").read_text(encoding="utf-8"))
    if not frames:
        fail("no frames were extracted")
    for frame in frames:
        frame_path = analysis / frame["path"]
        if not frame_path.is_file() or frame_path.stat().st_size == 0:
            fail(f"missing extracted frame: {frame_path}")
        if sha256(frame_path) != frame.get("sha256"):
            fail(f"frame hash mismatch: {frame_path}")

    probe = json.loads((analysis / "probe.json").read_text(encoding="utf-8"))
    if float(probe.get("duration_seconds", 0)) <= 0:
        fail("ffprobe did not report a positive duration")

    required_candidate = ["SKILL.md", "PREVIEW.md", "generation-report.json", "APPROVAL.md"]
    for name in required_candidate:
        if not (candidate / name).is_file():
            fail(f"candidate lifecycle artifact missing: {name}")

    installed_skill = installed / "real-world-video-skill" / "SKILL.md"
    if not installed_skill.is_file():
        fail("approved candidate was not installed into the skills directory")

    if not archive.is_file() or archive.stat().st_size == 0:
        fail("package archive was not created")
    with zipfile.ZipFile(archive) as zf:
        if "real-world-video-skill/SKILL.md" not in zf.namelist():
            fail("packaged ZIP does not contain the generated skill")

    evidence = {
        "source_url": manifest.get("source_display"),
        "downloaded_media": str(media),
        "downloaded_bytes": media.stat().st_size,
        "media_sha256": manifest.get("media_sha256"),
        "duration_seconds": probe.get("duration_seconds"),
        "transcript_method": transcript_method,
        "transcript_cues": len(transcript),
        "frames": len(frames),
        "ocr_records": len(json.loads((analysis / "ocr.json").read_text(encoding="utf-8"))),
        "candidate_generated": True,
        "candidate_approved": True,
        "candidate_installed": True,
        "candidate_packaged": True,
    }
    Path("real-world-evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
