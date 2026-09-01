from video_to_skill.analyze.claims import candidate_claims

def test_claim_candidates_keep_evidence():
    cues = [
        {"id": "VID-001", "text": "This tool requires Python."},
        {"id": "VID-002", "text": "Welcome to the course."},
    ]
    claims = candidate_claims(cues)
    assert len(claims) == 1
    assert claims[0]["evidence"] == ["VID-001"]
    assert claims[0]["status"] == "not-researched"

