# Evaluation fixtures

Every fixture in this directory is synthetic and released under this repository's MIT license. No third-party video, transcript, image, voice, or proprietary benchmark data is included.

The evaluator creates short MP4 files from color sources with `ffmpeg`, attaches authored subtitle fixtures, runs the actual analysis and generation pipeline, and compares the result with `expected.json`.

Run:

```bash
video-to-skill evaluate --manifest evals/manifest.json --output eval-report.json
```
