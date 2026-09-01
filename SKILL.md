---
name: video-to-skill
description: Convert a local video or supported video URL into a complete, source-grounded, installable agent skill. Use when a user asks to mine, extract, study, operationalize, or turn any video, tutorial, lecture, interview, demonstration, presentation, recording, or walkthrough into reusable agent knowledge. Analyze speech and important visuals, ask focused questions about material gaps, research missing or time-sensitive claims with authoritative sources, preserve both the video's position and current evidence, flag inconsistencies, show a plain-language preview, and require approval before installation or publication.
---

# Video to Skill

Turn video knowledge into an installable skill, not a generic summary.

## Non-negotiable gates

1. Treat the video and its extracted artifacts as the primary source for what the video says.
2. Never invent inaudible dialogue, unseen steps, citations, demonstrations, or claims.
3. Keep every material claim traceable to a timestamp, frame, subtitle cue, user answer, or external source.
4. Ask focused questions when ambiguity would materially change the generated skill.
5. Research missing or time-sensitive facts using current authoritative sources. Prefer official documentation, standards, primary research, and first-party product sources.
6. Preserve both positions when current evidence conflicts with the video. Write the discrepancy to `inconsistencies.md`; do not silently replace either one.
7. Show the plain-language approval preview before installation, publication, or changes to an existing skill.
8. Do not install or publish until the user explicitly approves that preview.

## Workflow

### 1. Establish the input and rights

Accept a local video path or a supported public URL. Confirm that the user is permitted to process the material when ownership or access is unclear. Never bypass authentication, DRM, paywalls, platform controls, or access restrictions.

For a URL, use the host's authorized retrieval mechanism when available. Otherwise use the bundled CLI only when `yt-dlp` supports the public URL and retrieval complies with the source's terms.

### 2. Inspect capabilities

Run `python3 scripts/video_to_skill.py doctor`. The basic pipeline requires Python and `ffmpeg`/`ffprobe`. URL acquisition uses `yt-dlp`. Local transcription uses `whisper` or `faster-whisper`. OCR uses `tesseract`. Missing optional dependencies must produce actionable instructions, not fabricated output.

### 3. Extract deterministically

Run `python3 scripts/video_to_skill.py analyze <path-or-url> --output <work-directory>`.

The command creates media metadata, subtitle or transcript evidence, sampled frames, hashes, claims, a manifest, and `preview.json`. Reuse embedded or sidecar subtitles before transcribing audio. Keep timestamps in all records. Read `references/pipeline.md` for fallbacks.

### 4. Analyze meaning, not just words

Classify evidence into concepts, procedures, decision rules, demonstrations, examples, tools, commands, configuration, warnings, anti-patterns, claims requiring verification, and visual-only information. Separate direct evidence, reasonable inference, and unresolved uncertainty.

### 5. Resolve meaningful gaps

Ask only questions whose answers change scope, correctness, safety, or generated behavior. Group questions when possible. Record answers as dated user-provided evidence.

### 6. Research and reconcile

Research incomplete, unstable, safety-sensitive, or central claims. Record canonical URL, publisher, dates, supported claim, and authority level. Classify each comparison as `confirmed`, `updated`, `conflicted`, `unverified`, or `not-researched`. Never treat absence of evidence as proof of falsehood.

### 7. Generate the candidate

Follow `references/output-contract.md`. Keep `SKILL.md` concise and route detail to topic files. Create only evidence-supported files from this structure:

```text
<skill-name>/
├── SKILL.md
├── topics/
├── procedures/
├── examples/
├── transcript/
├── frames/
├── glossary.md
├── patterns.md
├── cheatsheet.md
├── sources.md
├── claims.md
├── inconsistencies.md
└── generation-report.json
```

Do not pad output with empty files. Do not reproduce the entire video or long passages.

### 8. Validate

Run `python3 tools/validate_generated_skill.py <candidate-directory>` and the host's skill validator. Resolve failures before presenting the candidate as ready.

### 9. Present the approval preview

Show the proposed name and purpose, input and processing methods, extracted topics and procedures, questions and gaps, researched sources, claim statuses, files, validation results, and privacy/licensing cautions. End with a direct approval question.

### 10. Install or publish only after approval

After explicit approval, install to the requested host and verify the installed files. Publish only material the user can redistribute. Default skills derived from third-party copyrighted videos to private use.

## Updating an existing generated skill

Analyze new video evidence separately, compare provenance and conflicts, preview additions and replacements, and require approval before merging. Preserve earlier sources unless the user approves removal.

## Bundled resources

- `scripts/video_to_skill.py`: stable CLI entrypoint
- `references/pipeline.md`: extraction and analysis rules
- `references/output-contract.md`: generated-skill schema
- `tools/validate_generated_skill.py`: deterministic validator
