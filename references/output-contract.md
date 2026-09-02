# Generated skill output contract

## Required files

- `SKILL.md`: valid `name` and `description` frontmatter plus operational instructions.
- `sources.md`: video identity, hashes, timestamps, and external sources.
- `claims.md`: material claims with evidence and verification status.
- `inconsistencies.md`: conflicts, updates, and unresolved ambiguity.
- `generation-report.json`: provenance, processing methods, validation, gaps, and approval state.
- `PREVIEW.md`: plain-language candidate summary shown before approval.
- `references/knowledge.md`: evidence-linked topics, procedures, and examples.

Create topic, procedure, example, transcript, frame, glossary, pattern, and cheatsheet files only when evidence supports useful content.

## Evidence identifiers

Use zero-padded identifiers such as `VID-001` for video statements, `FRM-001` for visuals/OCR, `USR-001` for user answers, `WEB-001` for researched sources, and `INF-001` for labeled inference. Identifiers may expand beyond three digits for large courses. Every material factual instruction must cite evidence resolvable in `sources.md` or the report.

Generated candidates include `redaction-report.json`. Learning and hybrid candidates also include `references/learning-guide.md`. Multi-source candidates list `SRC-###` source provenance and course coverage in `sources.md`; incomplete coverage must remain visible in `PREVIEW.md` and `generation-report.json`.

## Conflict records

Include video claim, current-source claim, identifiers, classification, confidence, and effect on the generated skill. Preserve both positions.

## Copyright and privacy

Do not include source videos, full transcripts by default, long passages, faces, private details, credentials, or copyrighted frames unless necessary and permitted. Prefer synthesis and timestamp indexes.

## Lifecycle states

- `candidate-ready`: generated and integrity-hashed, but not approved.
- `approved`: explicitly approved against the recorded candidate digest.
- Installed and packaged copies must match the approved digest.

Approval is authenticated with a local HMAC key stored with owner-only permissions. Any change to `SKILL.md`, `PREVIEW.md`, knowledge, claims, sources, or inconsistencies after generation invalidates approval. `APPROVAL.md` is a signed receipt created after approval.
