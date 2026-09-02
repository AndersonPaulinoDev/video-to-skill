import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

from ..exceptions import VideoToSkillError
from ..provenance import write_json
from ..redaction import Redactor
from ..sanitize import sanitize_text

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_EVIDENCE = re.compile(r"^(?:VID|FRM|USR|WEB|INF)-\d{3,6}$")
_STATUSES = {"confirmed", "updated", "conflicted", "unverified", "not-researched"}
_MODES = {"operational", "learning", "hybrid", "reference"}


def _read_json(path: Path) -> dict | list:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VideoToSkillError(f"Invalid JSON file {path}: {exc}") from exc


def _load_analysis(workdir: Path) -> tuple[dict, list[dict], list[dict], list[dict], list[dict]]:
    required = ("manifest.json", "claims.json", "frames.json", "ocr.json", "transcript.jsonl")
    missing = [name for name in required if not (workdir / name).is_file()]
    if missing:
        raise VideoToSkillError(f"Analysis directory is missing: {', '.join(missing)}")
    manifest = _read_json(workdir / "manifest.json")
    claims = _read_json(workdir / "claims.json")
    frames = _read_json(workdir / "frames.json")
    ocr = _read_json(workdir / "ocr.json")
    cues = []
    for number, line in enumerate((workdir / "transcript.jsonl").read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            cues.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise VideoToSkillError(f"Invalid transcript JSON on line {number}") from exc
    if not isinstance(manifest, dict) or not all(isinstance(value, list) for value in (claims, frames, ocr)):
        raise VideoToSkillError("Analysis artifacts have invalid top-level types")
    return manifest, claims, frames, ocr, cues


def _validate_research(payload: dict, claim_ids: set[str]) -> tuple[list[dict], dict[str, dict]]:
    if not isinstance(payload, dict):
        raise VideoToSkillError("Research input must be a JSON object")
    sources = payload.get("sources", [])
    findings = payload.get("claims", [])
    if not isinstance(sources, list) or not isinstance(findings, list):
        raise VideoToSkillError("Research sources and claims must be arrays")
    source_ids = set()
    clean_sources = []
    for source in sources:
        if not isinstance(source, dict):
            raise VideoToSkillError("Every research source must be an object")
        source_id = source.get("id")
        url = source.get("url", "")
        parsed = urlparse(url)
        if not isinstance(source_id, str) or not re.fullmatch(r"WEB-\d{3,6}", source_id):
            raise VideoToSkillError(f"Invalid research source id: {source_id}")
        if source_id in source_ids:
            raise VideoToSkillError(f"Duplicate research source id: {source_id}")
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
            raise VideoToSkillError(f"Invalid research source URL for {source_id}")
        sensitive_keys = {"access_token", "api_key", "apikey", "auth", "key", "signature", "token"}
        if any(key.lower() in sensitive_keys for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
            raise VideoToSkillError(f"Research source URL for {source_id} contains a sensitive query parameter")
        source_ids.add(source_id)
        clean_sources.append({
            "id": source_id,
            "title": sanitize_text(str(source.get("title", "Untitled source"))).strip(),
            "url": url,
            "publisher": sanitize_text(str(source.get("publisher", "Unknown publisher"))).strip(),
            "published_at": source.get("published_at"),
            "accessed_at": source.get("accessed_at"),
        })
    by_claim = {}
    for finding in findings:
        if not isinstance(finding, dict):
            raise VideoToSkillError("Every research claim must be an object")
        claim_id = finding.get("claim_id")
        status = finding.get("status")
        evidence = finding.get("evidence", [])
        if claim_id not in claim_ids:
            raise VideoToSkillError(f"Research references unknown claim: {claim_id}")
        if claim_id in by_claim:
            raise VideoToSkillError(f"Duplicate research result for claim: {claim_id}")
        if status not in _STATUSES - {"not-researched"}:
            raise VideoToSkillError(f"Invalid research status for {claim_id}: {status}")
        if not isinstance(evidence, list) or any(item not in source_ids for item in evidence):
            raise VideoToSkillError(f"Research evidence for {claim_id} must reference declared WEB ids")
        current_finding = sanitize_text(str(finding.get("current_finding", ""))).strip()
        if status in {"confirmed", "updated", "conflicted"} and (not evidence or not current_finding):
            raise VideoToSkillError(f"Research result for {claim_id} requires evidence and a current finding")
        by_claim[claim_id] = {
            "status": status,
            "current_finding": current_finding,
            "evidence": evidence,
            "confidence": finding.get("confidence"),
        }
    return clean_sources, by_claim


def _validate_knowledge(payload: dict, known_evidence: set[str]) -> dict:
    if not isinstance(payload, dict):
        raise VideoToSkillError("Knowledge input must be a JSON object")
    clean = {"purpose": sanitize_text(str(payload.get("purpose", ""))).strip()}
    for section in ("topics", "procedures", "examples"):
        records = payload.get(section, [])
        if not isinstance(records, list):
            raise VideoToSkillError(f"Knowledge {section} must be an array")
        clean_records = []
        for record in records:
            if not isinstance(record, dict):
                raise VideoToSkillError(f"Every {section} record must be an object")
            evidence = record.get("evidence", [])
            if not evidence or not isinstance(evidence, list) or any(
                not isinstance(item, str) or not _EVIDENCE.fullmatch(item) or item not in known_evidence
                for item in evidence
            ):
                raise VideoToSkillError(f"Knowledge {section} contains unknown evidence")
            clean_record = {
                "title": sanitize_text(str(record.get("title", "Untitled"))).strip(),
                "summary": sanitize_text(str(record.get("summary", ""))).strip(),
                "content": sanitize_text(str(record.get("content", ""))).strip(),
                "evidence": evidence,
            }
            if not clean_record["title"] or not (clean_record["summary"] or clean_record["content"] or record.get("steps")):
                raise VideoToSkillError(f"Knowledge {section} records require a title and content")
            steps = record.get("steps", [])
            if steps and not isinstance(steps, list):
                raise VideoToSkillError("Procedure steps must be an array")
            clean_record["steps"] = []
            for step in steps:
                if not isinstance(step, dict):
                    raise VideoToSkillError("Every procedure step must be an object")
                step_evidence = step.get("evidence", [])
                if not step_evidence or not isinstance(step_evidence, list) or any(
                    item not in known_evidence for item in step_evidence
                ):
                    raise VideoToSkillError("Procedure step contains unknown evidence")
                step_text = sanitize_text(str(step.get("text", ""))).strip()
                if not step_text:
                    raise VideoToSkillError("Procedure step text cannot be empty")
                clean_record["steps"].append({
                    "text": step_text,
                    "evidence": step_evidence,
                })
            clean_records.append(clean_record)
        clean[section] = clean_records
    questions = payload.get("unresolved_questions", [])
    if not isinstance(questions, list):
        raise VideoToSkillError("unresolved_questions must be an array")
    clean["unresolved_questions"] = [sanitize_text(str(item)).strip() for item in questions if str(item).strip()]
    return clean


def _refs(items: list[str]) -> str:
    return ", ".join(f"`{item}`" for item in items) if items else "No evidence supplied"


def candidate_digest(root: Path) -> str:
    digest = hashlib.sha256()
    excluded = {"generation-report.json", "APPROVAL.md"}
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name not in excluded):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _write_sources(path: Path, manifest: dict, cues: list[dict], frames: list[dict],
                   ocr: list[dict], sources: list[dict], evidence_used: set[str]) -> None:
    lines = [
        "# Sources", "", "## Video source", "",
        f"- Source set: {manifest['source_display']}",
        f"- Source kind: {manifest['source_kind']}",
        f"- Processed: {manifest['created_at']}", "",
    ]
    video_sources = manifest.get("sources") or [{
        "id": "SRC-001", "display": manifest["source_display"],
        "sha256": manifest["media_sha256"],
    }]
    lines.extend(["| Source ID | Display | SHA-256 |", "|---|---|---|"])
    for source in video_sources:
        display = sanitize_text(str(source.get("display", "Unknown source"))).replace("|", "\\|")
        lines.append(f"| `{source.get('id', 'SRC-001')}` | {display} | `{source.get('sha256', '')}` |")
    coverage = manifest.get("coverage")
    if coverage:
        lines.extend([
            "", "## Source coverage", "",
            f"- Expected: {coverage.get('expected_sources', 0)}",
            f"- Completed: {coverage.get('completed_sources', 0)}",
            f"- Failed or inaccessible: {coverage.get('failed_sources', 0)}",
        ])
        for missing in coverage.get("unresolved_sources", []):
            lines.append(
                f"- Unresolved `{missing.get('id', 'unknown')}`: "
                f"{sanitize_text(str(missing.get('title', 'Unknown source')))}"
            )
    lines.extend(["",
        "## Timestamped video evidence", "",
        "| ID | Source | Time | Excerpt |", "|---|---|---:|---|",
    ])
    for cue in cues:
        if cue["id"] not in evidence_used:
            continue
        excerpt = sanitize_text(cue.get("text", "")).replace("|", "\\|").strip()[:240]
        lines.append(
            f"| `{cue['id']}` | `{cue.get('source_id', 'SRC-001')}` | "
            f"{float(cue.get('start', 0)):.1f}s | {excerpt} |"
        )
    lines.extend(["", "## Visual evidence", "", "| ID | Source | Time | SHA-256 | OCR |", "|---|---|---:|---|---|"])
    ocr_by_id = {item["id"]: item.get("text", "") for item in ocr}
    for frame in frames:
        if frame["id"] not in evidence_used:
            continue
        text = sanitize_text(ocr_by_id.get(frame["id"], "")).replace("|", "\\|").strip()[:160]
        lines.append(
            f"| `{frame['id']}` | `{frame.get('source_id', 'SRC-001')}` | "
            f"{float(frame.get('timestamp', 0)):.1f}s | `{frame.get('sha256', '')}` | {text or '—'} |"
        )
    lines.extend(["", "## External research", ""])
    if not sources:
        lines.append("No external research sources were supplied.")
    for source in sources:
        dates = ", ".join(value for value in (source.get("published_at"), source.get("accessed_at")) if value)
        suffix = f" ({dates})" if dates else ""
        lines.append(f"- `{source['id']}` [{source['title']}]({source['url']}) — {source['publisher']}{suffix}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_claims(path: Path, claims: list[dict]) -> None:
    lines = ["# Claims", ""]
    if not claims:
        lines.append("No material claims were detected.")
    for claim in claims:
        lines.extend([
            f"## {claim['id']}: {claim['status']}", "", claim["text"], "",
            f"- Video evidence: {_refs(claim.get('evidence', []))}",
            f"- Research evidence: {_refs(claim.get('research_evidence', []))}",
            f"- Current finding: {claim.get('current_finding') or 'Not supplied'}",
            f"- Confidence: {claim.get('confidence') or 'Not supplied'}", "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_inconsistencies(path: Path, claims: list[dict], questions: list[str]) -> None:
    conflicts = [item for item in claims if item["status"] in {"updated", "conflicted", "unverified", "not-researched"}]
    lines = ["# Inconsistencies and unresolved items", ""]
    if not conflicts and not questions:
        lines.append("No inconsistencies or unresolved questions were identified.")
    for claim in conflicts:
        lines.extend([
            f"## {claim['id']}: {claim['status']}", "",
            f"- Video position: {claim['text']}",
            f"- Current evidence: {claim.get('current_finding') or 'No authoritative finding supplied'}",
            f"- Evidence: {_refs(claim.get('evidence', []) + claim.get('research_evidence', []))}", "",
        ])
    if questions:
        lines.extend(["## Unresolved questions", ""])
        lines.extend(f"- {question}" for question in questions)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_knowledge(path: Path, knowledge: dict, claims: list[dict]) -> None:
    lines = ["# Operational knowledge", ""]
    if knowledge.get("purpose"):
        lines.extend([knowledge["purpose"], ""])
    for topic in knowledge.get("topics", []):
        lines.extend([f"## {topic['title']}", "", topic["summary"] or topic["content"],
                      "", f"Evidence: {_refs(topic['evidence'])}", ""])
    for procedure in knowledge.get("procedures", []):
        lines.extend([f"## Procedure: {procedure['title']}", ""])
        if procedure["summary"]:
            lines.extend([procedure["summary"], ""])
        for index, step in enumerate(procedure["steps"], 1):
            lines.append(f"{index}. {step['text']} ({_refs(step['evidence'])})")
        lines.append("")
    for example in knowledge.get("examples", []):
        lines.extend([f"## Example: {example['title']}", "", example["content"] or example["summary"],
                      "", f"Evidence: {_refs(example['evidence'])}", ""])
    if not any(knowledge.get(section) for section in ("topics", "procedures", "examples")):
        lines.extend(["## Extracted claims", ""])
        for claim in claims:
            lines.append(f"- {claim['text']} ({_refs(claim.get('evidence', []))}; status: `{claim['status']}`)")
        if not claims:
            lines.append("No operational knowledge was supplied. Review the source evidence before using this skill.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _mode_rules(mode: str) -> list[str]:
    if mode == "learning":
        return [
            "Use `references/learning-guide.md` to diagnose, teach, quiz, practice, and review.",
            "Reveal answers after the learner attempts a question unless they ask for direct instruction.",
        ]
    if mode == "hybrid":
        return [
            "Choose operational guidance or the learning workflow based on the user's request.",
            "For teaching and practice, follow `references/learning-guide.md`.",
        ]
    if mode == "reference":
        return [
            "Answer as a concise source reference; retrieve only the relevant grounded section.",
            "Do not create exercises unless the user explicitly requests them.",
        ]
    return ["Apply the source-grounded procedure directly to the user's work when appropriate."]


def _write_learning_guide(path: Path, knowledge: dict) -> None:
    units = [record["title"] for section in ("topics", "procedures", "examples")
             for record in knowledge.get(section, [])]
    lines = [
        "# Learning guide", "",
        "Use a short diagnostic before teaching, then adapt depth to the learner's demonstrated understanding.", "",
        "## Learning loop", "",
        "1. Ask one or two diagnostic questions grounded in the source.",
        "2. Teach one unit with its evidence identifiers.",
        "3. Give a retrieval question or practical exercise.",
        "4. Review the attempt against the source and explain corrections.",
        "5. Continue or revisit the weak point.", "",
        "## Available units", "",
    ]
    lines.extend(f"- {unit}" for unit in units)
    if not units:
        lines.append("- Extracted claims and evidence in `references/knowledge.md`")
    lines.extend(["", "Never invent course content, scores, or answer keys absent from the evidence."])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _publication_manifest(manifest: dict) -> dict:
    clean = json.loads(json.dumps(manifest))

    def display(value: str) -> str:
        parsed = urlparse(value)
        if not parsed.scheme and Path(value).is_absolute():
            return Path(value).name
        return value

    clean["source_display"] = display(str(clean.get("source_display", "Unknown source")))
    for source in clean.get("sources", []):
        source["display"] = display(str(source.get("display", "Unknown source")))
    coverage = clean.get("coverage")
    if coverage:
        coverage["unresolved_sources"] = [
            {"id": item.get("id", "unknown"), "title": item.get("title", "Unknown source")}
            for item in coverage.get("unresolved_sources", [])
        ]
    return clean


def generate_candidate(workdir: Path, output: Path, name: str, description: str,
                       research_path: Path | None = None, knowledge_path: Path | None = None,
                       mode: str = "operational", redact_pii: bool = True,
                       redact_names: list[str] | None = None) -> dict:
    if not _SLUG.fullmatch(name) or len(name) > 64:
        raise VideoToSkillError("Skill name must be a lowercase hyphenated slug of at most 64 characters")
    description = sanitize_text(description).strip()
    if not description:
        raise VideoToSkillError("Skill description cannot be empty")
    if mode not in _MODES:
        raise VideoToSkillError(f"Unsupported generated-skill mode: {mode}")
    if output.is_symlink():
        raise VideoToSkillError("Candidate output cannot be a symbolic link")
    if output.exists():
        if not output.is_dir():
            raise VideoToSkillError(f"Candidate output is not a directory: {output}")
        if any(output.iterdir()):
            raise VideoToSkillError(f"Candidate directory is not empty: {output}")
    manifest, claims, frames, ocr, cues = _load_analysis(workdir)
    if manifest.get("status") != "extracted":
        raise VideoToSkillError("Analysis is partial; resolve transcript gaps before generation")
    claim_ids = {item["id"] for item in claims}
    sources, research = _validate_research(_read_json(research_path), claim_ids) if research_path else ([], {})
    for claim in claims:
        finding = research.get(claim["id"], {})
        claim["status"] = finding.get("status", claim.get("status", "not-researched"))
        claim["current_finding"] = finding.get("current_finding", "")
        claim["research_evidence"] = finding.get("evidence", [])
        claim["confidence"] = finding.get("confidence")
    known_evidence = {
        *(item["id"] for item in cues), *(item["id"] for item in frames),
        *(item["id"] for item in sources),
    }
    knowledge = _validate_knowledge(_read_json(knowledge_path), known_evidence) if knowledge_path else {
        "purpose": "", "topics": [], "procedures": [], "examples": [], "unresolved_questions": []
    }
    redactor = Redactor(enabled=redact_pii, names=redact_names or [])
    description = redactor.redact(description)
    manifest = redactor.redact_data(_publication_manifest(manifest))
    claims = redactor.redact_data(claims)
    frames = redactor.redact_data(frames)
    ocr = redactor.redact_data(ocr)
    cues = redactor.redact_data(cues)
    sources = redactor.redact_data(sources)
    knowledge = redactor.redact_data(knowledge)
    output.mkdir(parents=True, exist_ok=True)
    references = output / "references"
    references.mkdir()
    skill = [
        "---", f"name: {name}", f"description: {json.dumps(description, ensure_ascii=False)}", "---", "",
        f"# {name.replace('-', ' ').title()}", "",
        "Use this skill only for work covered by the source-grounded knowledge in this package.", "",
        "## Operating rules", "",
        "1. Read `references/knowledge.md` for the extracted guidance relevant to the request.",
        "2. Check `claims.md` before relying on factual or time-sensitive statements.",
        "3. Read `inconsistencies.md` when a claim is updated, conflicted, unverified, or not researched.",
        "4. Preserve the distinction between video evidence and external research.",
        "5. Do not extend the source beyond its evidence; label new inference explicitly.", "",
        "## Usage mode", "",
        f"This package uses `{mode}` mode.", "",
        *[f"- {rule}" for rule in _mode_rules(mode)], "",
        "## Evidence", "",
        "Use `sources.md` to resolve VID, FRM, and WEB identifiers. Material guidance in this package is traceable to those identifiers.", "",
    ]
    (output / "SKILL.md").write_text("\n".join(skill), encoding="utf-8")
    evidence_used = {item for claim in claims for item in claim.get("evidence", [])}
    for section in ("topics", "procedures", "examples"):
        for record in knowledge.get(section, []):
            evidence_used.update(record.get("evidence", []))
            for step in record.get("steps", []):
                evidence_used.update(step.get("evidence", []))
    _write_sources(output / "sources.md", manifest, cues, frames, ocr, sources, evidence_used)
    _write_claims(output / "claims.md", claims)
    _write_inconsistencies(output / "inconsistencies.md", claims, knowledge["unresolved_questions"])
    _write_knowledge(references / "knowledge.md", knowledge, claims)
    if mode in {"learning", "hybrid"}:
        _write_learning_guide(references / "learning-guide.md", knowledge)
    unresolved = [item["id"] for item in claims if item["status"] in {"unverified", "not-researched"}]
    expected_files = [
        "PREVIEW.md", "SKILL.md", "claims.md", "generation-report.json",
        "inconsistencies.md", "references/knowledge.md", "sources.md",
        "redaction-report.json",
    ]
    if mode in {"learning", "hybrid"}:
        expected_files.append("references/learning-guide.md")
        expected_files.sort()
    write_json(output / "redaction-report.json", redactor.report())
    source_count = len(manifest.get("sources") or [manifest])
    coverage = manifest.get("coverage", {
        "expected_sources": source_count, "completed_sources": source_count,
        "failed_sources": 0, "complete": True, "unresolved_sources": [],
    })
    unresolved_sources = [item.get("id", "unknown") for item in coverage.get("unresolved_sources", [])]
    preview = [
        f"# Approval preview: {name}", "",
        f"- Purpose: {description}",
        f"- Source set: {manifest['source_display']} ({source_count} source{'s' if source_count != 1 else ''})",
        f"- Usage mode: {mode}",
        f"- PII redaction: {'enabled' if redact_pii else 'disabled by explicit option'}",
        f"- Source coverage: {coverage.get('completed_sources', source_count)}/{coverage.get('expected_sources', source_count)} completed",
        f"- Evidence: {len(cues)} transcript cues, {len(frames)} frames, {len(claims)} claims",
        f"- Research: {len(sources)} external sources",
        f"- Unresolved claims: {len(unresolved)}",
        f"- Unresolved questions: {len(knowledge['unresolved_questions'])}", "",
        "## Files", "",
        *(f"- `{file_name}`" for file_name in expected_files),
        "", "Approval status is recorded separately after explicit approval.",
    ]
    (output / "PREVIEW.md").write_text("\n".join(preview) + "\n", encoding="utf-8")
    report = {
        "schema_version": 2,
        "state": "candidate-ready",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "name": name,
        "source": {"display": manifest["source_display"], "sha256": manifest["media_sha256"],
                   "count": source_count},
        "mode": mode,
        "redaction": redactor.report(),
        "inputs": {"research_supplied": bool(research_path), "knowledge_supplied": bool(knowledge_path)},
        "counts": {"cues": len(cues), "frames": len(frames), "claims": len(claims),
                   "course_sources": source_count, "research_sources": len(sources)},
        "unresolved_claims": unresolved,
        "unresolved_questions": knowledge["unresolved_questions"],
        "unresolved_sources": unresolved_sources,
        "coverage": coverage,
        "files": expected_files,
        "approval": {"approved": False, "approved_at": None, "approved_by": None,
                     "accepted_unresolved": False, "approved_digest": None, "signature": None},
    }
    write_json(output / "generation-report.json", report)
    report["candidate_digest"] = candidate_digest(output)
    write_json(output / "generation-report.json", report)
    return report
