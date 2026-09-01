import re

_BIDI = re.compile("[\u202a-\u202e\u2066-\u2069]")
_CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

def sanitize_text(value: str) -> str:
    return _CONTROL.sub("", _BIDI.sub("", value)).replace("\r\n", "\n").replace("\r", "\n")

