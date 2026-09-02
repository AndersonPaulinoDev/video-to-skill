# Architecture

The extraction layer resolves the source, records metadata and hashes, extracts timestamped speech, samples visual evidence, runs optional OCR, and prepares candidate claims. The agent supplies evidence-linked `research.json` and `knowledge.json` records after questions and authoritative research. The generation layer validates those records and writes a digest-bound candidate. The lifecycle layer authenticates explicit approval with a protected local HMAC key, confines installation to the selected skills directory, verifies installed contents, and creates publication-safe ZIP packages only from approved candidates.

The evaluation layer generates tiny synthetic MP4 files from repository-owned specifications, attaches authored subtitles, runs the real analysis and generation pipeline, and scores observable outputs. Its weighted dimensions are analysis, structure, claim status, evidence, knowledge, conflict handling, and the closed approval gate. Every individual expectation must pass in addition to the numeric threshold, so a high aggregate cannot hide a safety regression.

The workspace layer records source identity, configuration, stage status, errors, and summaries in SQLite. Completed stages are reused only when the original source and extraction settings match and acquired media passes its digest check. `progress.json` exposes the same stage state without making JSON the recovery authority.

The visual layer analyzes bounded 9×8 RGB thumbnails to detect scene changes, combines those timestamps with periodic coverage, removes near-duplicates, and sends only retained frames to OCR. Agent-directed exact-frame and dense-window requests are capped, hashed, and promoted into the same evidence namespace.
