import json

from video_to_skill.cli import main

def test_doctor_outputs_json(capsys):
    assert main(["doctor"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "ready_for_local_video" in payload

def test_invalid_frame_values(capsys):
    code = main(["analyze", "missing.mp4", "--output", "out", "--max-frames", "0"])
    assert code == 2
    assert "must be positive" in capsys.readouterr().err

