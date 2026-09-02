# Changelog

## 1.0.0 - 2026-09-02 — First Public Release

This is the first public version of Video to Skill. Five earlier iterations were
private development milestones and are not part of the public version history.

- Added public playlist/course inventory and resumable per-source course analysis.
- Added deterministic multi-analysis merging with globally unique evidence identifiers.
- Preserved exact agreements as multi-source evidence and retained contradictory claims separately.
- Added explicit course coverage with failed-source disclosure and approval blocking.
- Added publication-time email, phone, government-ID, and explicit-name redaction by default.
- Added operational, learning, hybrid, and reference generated-skill modes.
- Added a fourth end-to-end privacy evaluation fixture and privacy regression scoring.
- Removed host-private absolute paths and source errors from generated publication artifacts.

## 0.4.0 - 2026-09-02

- Added SQLite-backed resumable analysis with six observable processing stages.
- Added progress reporting and source/configuration integrity checks for resumed runs.
- Added bounded RGB scene-change detection that catches isoluminant visual changes.
- Added near-duplicate frame suppression before OCR and semantic analysis.
- Added exact-frame and dense-window reinspection with a 60-frame context cap.
- Promoted selected reinspection frames into the normal `FRM-###` evidence contract.
- Required source-digest verification before every visual reinspection request.
- Added interrupted-run, changed-settings, scene-cut, deduplication, timestamp, and reinspection tests.

## 0.3.0 - 2026-09-02

- Added a deterministic end-to-end evaluation command and scoring engine.
- Added three repository-owned synthetic fixtures covering approval workflow, outdated claims, and Spanish subtitles.
- Added measurable regression thresholds for analysis, generated structure, claim status, evidence, knowledge, conflicts, and approval safety.
- Added positive, negative, boundary, and path-confinement evaluator tests.
- Bounded synthetic media dimensions and sampling to prevent fixture-driven CI exhaustion.
- Added the complete evaluation suite to CI.

## 0.2.0 - 2026-09-01

- Added complete `generate → approve → install/package` lifecycle.
- Added validated research and structured-knowledge input contracts.
- Added candidate integrity hashes and tamper-resistant approval.
- Added verified ZIP packaging and installation checks.
- Expanded lifecycle and security regression coverage.

## 0.1.0 - Unreleased

- Initial local-file and public-URL intake
- Media probing, subtitle parsing, local transcription fallback, frame sampling, and OCR
- Provenance hashes, candidate claims, research status contract, and approval preview
- Generated-skill contract and validator
- Tests, CI, security guidance, and documentation
