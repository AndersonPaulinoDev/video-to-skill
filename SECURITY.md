# Security policy

Report suspected vulnerabilities privately to the repository owner rather than opening a public issue containing exploit details.

Video files, subtitles, metadata, OCR, transcripts, and URLs are untrusted input. The project must not execute extracted commands, bypass access controls, accept URL-embedded credentials, overwrite non-empty output directories, or publish generated skills without approval. Temporary media and extracted frames may contain sensitive information; users should inspect and delete work directories when finished.

Approval is authenticated with a local key at `~/.config/video-to-skill/approval.key` by default. Protect and back up this file. Anyone who can read the key and modify candidate files can create a valid approval signature. Set `VIDEO_TO_SKILL_APPROVAL_KEY_FILE` to place it in another protected location. Candidate directories and their contents may not be symbolic links, and installed skill names are validated and confined to the selected skills directory.
