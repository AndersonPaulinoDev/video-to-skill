import shutil
import subprocess
from pathlib import Path

from ..sanitize import sanitize_text

def ocr_frames(frames: list[dict], root: Path) -> list[dict]:
    if not shutil.which("tesseract"):
        return []
    records = []
    for frame in frames:
        path = root / frame["path"]
        result = subprocess.run(["tesseract", str(path), "stdout"], capture_output=True, text=True)
        text = sanitize_text(result.stdout).strip()
        if text:
            records.append({"id": frame["id"], "timestamp": frame["timestamp"], "text": text,
                            "method": "tesseract"})
    return records
