from video_to_skill.redaction import Redactor


def test_redactor_removes_pii_and_explicit_names():
    redactor = Redactor(names=["Jane Doe"])

    result = redactor.redact(
        "Jane Doe: jane@example.com, 407-555-1212, SSN 123-45-6789."
    )

    assert result == (
        "[REDACTED_NAME]: [REDACTED_EMAIL], [REDACTED_PHONE], SSN [REDACTED_ID]."
    )
    assert redactor.report()["total_replacements"] == 4


def test_disabled_redactor_preserves_input():
    redactor = Redactor(enabled=False, names=["Jane Doe"])
    value = "Jane Doe at jane@example.com"

    assert redactor.redact(value) == value
    assert redactor.report()["total_replacements"] == 0
