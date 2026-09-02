# Courses, playlists, and multi-video skills

## Inventory before processing

Create a normalized inventory from a public playlist/course URL or an authored JSON source list:

```bash
python3 scripts/video_to_skill.py course-inventory <url-or-inventory.json> \
  --output course-inventory.json
```

An authored inventory uses:

```json
{
  "title": "Course title",
  "sources": [
    {"id": "SRC-001", "source": "lesson-1.mp4", "title": "Lesson 1"},
    {"id": "SRC-002", "source": "lesson-2.mp4", "title": "Lesson 2"}
  ]
}
```

Relative local paths resolve from the inventory file, not the calling directory.

## Analyze and merge

```bash
python3 scripts/video_to_skill.py course-analyze course-inventory.json \
  --output course-work
```

Each source gets an isolated resumable workspace under `course-work/analyses/`. Successful sources merge into `course-work/merged/`. `course-report.json` records expected, completed, and failed sources. Repeat with `--resume` after resolving transient failures.

Merge existing complete analyses directly when no inventory is needed:

```bash
python3 scripts/video_to_skill.py merge analysis-1 analysis-2 \
  --output merged-analysis \
  --title "Combined method"
```

Merging renumbers transcript and frame evidence globally, copies retained visual evidence, combines identical claims without losing source provenance, and keeps non-identical or contradictory claims separate for research reconciliation.

## Generate for the intended use

- `operational`: apply the extracted method to work.
- `learning`: diagnose, teach, quiz, practice, and review.
- `hybrid`: choose operational or learning behavior from the request.
- `reference`: retrieve concise source-grounded answers.

PII redaction is enabled by default for generated publication files. Add `--redact-name "Name"` for explicit names. Raw analysis evidence is not rewritten. Incomplete source coverage remains visible and blocks ordinary approval until the user explicitly accepts unresolved sources.
