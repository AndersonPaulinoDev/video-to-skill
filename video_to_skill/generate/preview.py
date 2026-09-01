def build_preview(manifest: dict, claims: list[dict], cues: list[dict], frames: list[dict]) -> dict:
    return {
        "state": "analysis-ready",
        "install_or_publish_allowed": False,
        "source": {"kind": manifest["source_kind"], "display": manifest["source_display"]},
        "processing": manifest["processing"],
        "evidence": {"transcript_cues": len(cues), "sampled_frames": len(frames), "candidate_claims": len(claims)},
        "research": {"required": True, "completed": False, "confirmed": 0, "updated": 0,
                     "conflicted": 0, "unverified": 0},
        "unresolved_gaps": manifest.get("unresolved_gaps", []),
        "next_action": "Agent review, questions, research, candidate generation, validation, then user approval.",
    }
