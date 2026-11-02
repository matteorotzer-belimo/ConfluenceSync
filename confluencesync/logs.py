"""Log file in the app data folder, without tokens or page content."""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_SECRET = re.compile(r"(Bearer\s+|token[\"'=:\s]+|secret_|ntn_)[A-Za-z0-9._\-~+/=]{6,}", re.IGNORECASE)


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = _SECRET.sub(lambda m: m.group(1) + "***", message)
        if redacted != message:
            record.msg, record.args = redacted, ()
        return True


def setup(log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "confluencesync.log"
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactFilter())
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    return path
