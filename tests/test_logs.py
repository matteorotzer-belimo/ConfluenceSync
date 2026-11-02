from __future__ import annotations

import logging

import pytest

from confluencesync import logs


def redact(msg: str, *args) -> str:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, msg, args, None)
    assert logs.RedactFilter().filter(record) is True
    return record.getMessage()


@pytest.mark.parametrize("message,secret,expected", [
    ("Authorization: Bearer abcDEF123.456-xyz", "abcDEF123.456-xyz", "Authorization: Bearer ***"),
    ("url?token=s3cr3tValue99&x=1", "s3cr3tValue99", "url?token=***&x=1"),
    ('{"token": "abcdef123456"}', "abcdef123456", '{"token": "***"}'),
    ("key secret_AbCdEf0123456789 used", "AbCdEf0123456789", "key secret_*** used"),
    ("notion ntn_1234567890abcdef ok", "1234567890abcdef", "notion ntn_*** ok"),
])
def test_secrets_are_redacted(message, secret, expected):
    result = redact(message)
    assert secret not in result
    assert result == expected


def test_redaction_of_formatting_arguments():
    result = redact("calling %s with %s", "https://confluence.example.com", "Bearer verySecretToken42")
    assert result == "calling https://confluence.example.com with Bearer ***"


def test_harmless_messages_are_unchanged():
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "published %s (%d)", ("Seite", 3), None)
    logs.RedactFilter().filter(record)
    assert record.args == ("Seite", 3)
    assert record.getMessage() == "published Seite (3)"
    assert redact("token abc") == "token abc"          # too short to be a secret


def test_setup_writes_redacted_log_file(tmp_path):
    root = logging.getLogger()
    before = list(root.handlers)
    level = root.level
    try:
        path = logs.setup(tmp_path / "logs")
        logging.getLogger("confluencesync.test").info("connect with Bearer pat-SECRET-0123456789")
        for handler in root.handlers:
            handler.flush()
    finally:
        for handler in root.handlers[:]:
            if handler not in before:
                root.removeHandler(handler)
                handler.close()
        root.setLevel(level)
    text = path.read_text(encoding="utf-8")
    assert path == tmp_path / "logs" / "confluencesync.log"
    assert "connect with Bearer ***" in text
    assert "pat-SECRET-0123456789" not in text
