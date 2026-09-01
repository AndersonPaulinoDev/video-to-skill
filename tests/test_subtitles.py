from video_to_skill.extract.subtitles import parse_subtitle

def test_parse_srt_and_sanitize(tmp_path):
    source = tmp_path / "clip.srt"
    source.write_text(
        "1\n00:00:01,000 --> 00:00:03,500\n<b>This is required.</b>\n\n"
        "2\n00:01:00,000 --> 00:01:02,000\nNever run it blindly.\n",
        encoding="utf-8",
    )
    cues = parse_subtitle(source)
    assert [cue["id"] for cue in cues] == ["VID-001", "VID-002"]
    assert cues[0]["start"] == 1.0
    assert cues[1]["start"] == 60.0
    assert cues[0]["text"] == "This is required."

