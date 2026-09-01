from video_to_skill.generate.preview import build_preview

def test_preview_blocks_install_and_publish():
    manifest = {"source_kind": "file", "source_display": "clip.mp4", "processing": {}, "unresolved_gaps": []}
    preview = build_preview(manifest, [], [], [])
    assert preview["install_or_publish_allowed"] is False
    assert preview["research"]["completed"] is False

