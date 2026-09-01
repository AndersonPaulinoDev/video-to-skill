import re
from pathlib import Path

from ..sanitize import sanitize_text

_TIME = re.compile(r"(?P<h>\d{1,2}):(?P<m>\d{2}):(?P<s>\d{2}[.,]\d{3})\s+-->\s+(?P<eh>\d{1,2}):(?P<em>\d{2}):(?P<es>\d{2}[.,]\d{3})")
_TAG = re.compile(r"<[^>]+>")

def _seconds(h: str, m: str, s: str) -> float:
    return int(h) * 3600 + int(m) * 60 + float(s.replace(",", "."))

def parse_subtitle(path: Path) -> list[dict]:
    lines = sanitize_text(path.read_text(encoding="utf-8", errors="replace")).splitlines()
    cues, index = [], 0
    while index < len(lines):
        match = _TIME.search(lines[index])
        if not match:
            index += 1
            continue
        content, index = [], index + 1
        while index < len(lines) and lines[index].strip():
            content.append(_TAG.sub("", lines[index]).strip())
            index += 1
        clean = " ".join(part for part in content if part)
        if clean:
            cues.append({
                "id": f"VID-{len(cues)+1:03d}",
                "start": _seconds(match["h"], match["m"], match["s"]),
                "end": _seconds(match["eh"], match["em"], match["es"]),
                "text": clean,
                "method": "subtitle",
            })
    return cues

def find_subtitle(media: Path) -> Path | None:
    candidates = sorted(media.parent.glob(f"{media.stem}*.vtt")) + sorted(media.parent.glob(f"{media.stem}*.srt"))
    return candidates[0] if candidates else None

