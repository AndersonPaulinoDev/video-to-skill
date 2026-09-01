import re

_CLAIM = re.compile(r"\b(is|are|will|must|should|requires?|supports?|cannot|always|never|best|latest)\b", re.I)

def candidate_claims(cues: list[dict]) -> list[dict]:
    claims = []
    for cue in cues:
        if _CLAIM.search(cue["text"]):
            claims.append({
                "id": f"CLM-{len(claims)+1:03d}", "text": cue["text"],
                "evidence": [cue["id"]], "status": "not-researched", "confidence": None,
            })
    return claims

