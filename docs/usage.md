# Usage

1. Run `video-to-skill doctor`.
2. Run `video-to-skill analyze <video> --output <analysis>`.
   If interrupted, run `video-to-skill progress <analysis>` and repeat the command with `--resume`.
3. Review the evidence and let the agent create validated `research.json` and `knowledge.json` files.
4. Run `video-to-skill generate <analysis> --output <candidate> --name <name> --description <description> --research <research.json> --knowledge <knowledge.json>`.
5. Review `<candidate>/PREVIEW.md` and the conflict report.
6. After explicit approval, run `video-to-skill approve <candidate> --by <approver>`.
7. Run `video-to-skill install <candidate> --skills-dir <directory>` or create a distributable archive with `video-to-skill package`.

Generation, approval, installation, and packaging are separate commands so approval cannot be bypassed accidentally.

## Evaluate a change

Run the repository-owned end-to-end suite before merging converter changes:

```bash
video-to-skill evaluate --manifest evals/manifest.json --output eval-report.json
```

The command exits unsuccessfully if the overall score is below the manifest threshold or any fixture expectation fails.

## Inspect visual evidence more closely

Use `video-to-skill inspect-frame <analysis> <timestamp>` for one ambiguous moment or `video-to-skill inspect-window <analysis> --start <timestamp> --end <timestamp> --fps 2` for a short sequence. Investigation outputs are bounded and added to the normal frame evidence set.
