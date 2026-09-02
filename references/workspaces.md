# Resumable workspaces and visual reinspection

Every analysis directory contains `workspace.sqlite3` as the authoritative processing state and `progress.json` as its readable projection. The six stages are `source`, `probe`, `transcript`, `frames`, `ocr`, and `finalize`.

## Resume an interrupted analysis

Inspect state:

```bash
python3 scripts/video_to_skill.py progress <work-directory>
```

Resume using the same source and extraction settings:

```bash
python3 scripts/video_to_skill.py analyze <path-or-url> \
  --output <work-directory> \
  --resume
```

The command rejects a changed source or configuration. It also verifies that previously acquired media still matches its SHA-256 digest. Start a new directory when intentionally changing settings or source media.

## Visual sampling

Baseline analysis combines periodic timestamps with RGB scene changes and removes visually redundant frames. Tune only when the defaults demonstrably miss or oversample meaningful states:

```bash
python3 scripts/video_to_skill.py analyze <video> \
  --output <work-directory> \
  --frame-interval 60 \
  --scene-threshold 0.32 \
  --dedup-threshold 6
```

Lower scene thresholds are more sensitive. Lower deduplication thresholds retain more similar frames.

## Reinspect an ambiguous moment

Extract one frame:

```bash
python3 scripts/video_to_skill.py inspect-frame <work-directory> 01:23.5
```

Inspect a short sequence:

```bash
python3 scripts/video_to_skill.py inspect-window <work-directory> \
  --start 01:20 \
  --end 01:26 \
  --fps 2
```

Window requests are capped at 60 frames and report truncation. Selected outputs are stored under `reinspection/`, hashed, appended to `frames.json`, assigned `FRM-###` identifiers, and become valid evidence for `knowledge.json`.
