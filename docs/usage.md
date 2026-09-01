# Usage

1. Run `video-to-skill doctor`.
2. Run `video-to-skill analyze <video> --output <analysis>`.
3. Review the evidence and let the agent create validated `research.json` and `knowledge.json` files.
4. Run `video-to-skill generate <analysis> --output <candidate> --name <name> --description <description> --research <research.json> --knowledge <knowledge.json>`.
5. Review `<candidate>/PREVIEW.md` and the conflict report.
6. After explicit approval, run `video-to-skill approve <candidate> --by <approver>`.
7. Run `video-to-skill install <candidate> --skills-dir <directory>` or create a distributable archive with `video-to-skill package`.

Generation, approval, installation, and packaging are separate commands so approval cannot be bypassed accidentally.
