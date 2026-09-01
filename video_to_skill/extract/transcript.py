import json
import shutil
import subprocess
from pathlib import Path

from ..exceptions import VideoToSkillError
from ..sanitize import sanitize_text
from .media import extract_audio

def transcribe(media: Path, workdir: Path) -> tuple[list[dict], str]:
    audio = extract_audio(media, workdir / "audio.wav")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        WhisperModel = None
    if WhisperModel is not None:
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(audio), vad_filter=True)
        cues = [{"id": f"VID-{i:03d}", "start": float(s.start), "end": float(s.end),
                 "text": sanitize_text(s.text.strip()), "method": "faster-whisper"}
                for i, s in enumerate(segments, 1) if s.text.strip()]
        return cues, "faster-whisper"
    if shutil.which("whisper"):
        command = ["whisper", str(audio), "--model", "small", "--output_format", "json",
                   "--output_dir", str(workdir)]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise VideoToSkillError((exc.stderr or "Whisper transcription failed").strip()) from exc
        payload = json.loads((workdir / "audio.json").read_text(encoding="utf-8"))
        cues = [{"id": f"VID-{i:03d}", "start": float(s["start"]), "end": float(s["end"]),
                 "text": sanitize_text(s["text"].strip()), "method": "whisper"}
                for i, s in enumerate(payload.get("segments", []), 1) if s.get("text", "").strip()]
        return cues, "whisper"
    raise VideoToSkillError("No subtitles were found and local transcription requires faster-whisper or whisper")

