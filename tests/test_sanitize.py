from video_to_skill.sanitize import sanitize_text

def test_control_and_bidi_characters_removed():
    assert sanitize_text("safe\u202eevil\x00") == "safeevil"

