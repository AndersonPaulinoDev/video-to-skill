from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from ..config import ALLOWED_URL_SCHEMES, SUPPORTED_LOCAL_EXTENSIONS, expand_path
from ..exceptions import VideoToSkillError

@dataclass(frozen=True)
class Source:
    kind: str
    value: str
    local_path: Path | None = None

def resolve_source(value: str) -> Source:
    parsed = urlparse(value)
    if parsed.scheme:
        if parsed.scheme not in ALLOWED_URL_SCHEMES:
            raise VideoToSkillError(f"Unsupported URL scheme: {parsed.scheme}")
        if parsed.username or parsed.password:
            raise VideoToSkillError("URLs containing credentials are not accepted")
        if not parsed.netloc:
            raise VideoToSkillError("URL is missing a host")
        return Source("url", value)
    path = expand_path(value)
    if not path.is_file():
        raise VideoToSkillError(f"Video file not found: {path}")
    if path.suffix.lower() not in SUPPORTED_LOCAL_EXTENSIONS:
        raise VideoToSkillError(f"Unsupported video extension: {path.suffix or '(none)'}")
    return Source("file", str(path), path)

