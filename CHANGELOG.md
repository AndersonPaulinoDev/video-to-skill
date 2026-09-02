# Changelog

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
