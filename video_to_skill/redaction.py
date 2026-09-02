import re
from dataclasses import dataclass, field


_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w-])")
_PHONE = re.compile(r"(?<!\d)(?:\+?1[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]?\d{4}(?!\d)")
_SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")


@dataclass
class Redactor:
    enabled: bool = True
    names: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=lambda: {
        "email": 0, "phone": 0, "government_id": 0, "explicit_name": 0,
    })

    def redact(self, value: str) -> str:
        if not self.enabled:
            return value
        value = self._replace(_EMAIL, value, "[REDACTED_EMAIL]", "email")
        value = self._replace(_PHONE, value, "[REDACTED_PHONE]", "phone")
        value = self._replace(_SSN, value, "[REDACTED_ID]", "government_id")
        for name in self.names:
            clean = name.strip()
            if not clean:
                continue
            pattern = re.compile(rf"(?<!\w){re.escape(clean)}(?!\w)", re.IGNORECASE)
            value = self._replace(pattern, value, "[REDACTED_NAME]", "explicit_name")
        return value

    def redact_data(self, value):
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, list):
            return [self.redact_data(item) for item in value]
        if isinstance(value, dict):
            return {key: self.redact_data(item) for key, item in value.items()}
        return value

    def report(self) -> dict:
        return {
            "schema_version": 1,
            "enabled": self.enabled,
            "explicit_names_configured": len([name for name in self.names if name.strip()]),
            "replacements": self.counts,
            "total_replacements": sum(self.counts.values()),
            "note": "Counts describe generated publication files; raw analysis evidence is unchanged.",
        }

    def _replace(self, pattern: re.Pattern, value: str, replacement: str, category: str) -> str:
        def replace(_match):
            self.counts[category] += 1
            return replacement

        return pattern.sub(replace, value)
