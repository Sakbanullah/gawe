"""Logging with redaction.

Operational logs carry metadata only: no CV content, prompt, model response,
email, phone, or URL query string.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE_RE = re.compile(r"(?<!\w)(?:\+62|62|0)8[1-9][0-9]{6,10}(?!\w)")
URL_QUERY_RE = re.compile(r"(https?://[^\s?#]+)\?[^\s#]*")
SECRET_RE = re.compile(r"(?i)\b(api[_-]?key|secret|token)\b\s*[=:]\s*\S+")

REDACTED = "[redacted]"


def redact(text: str) -> str:
    """Redact email, phone, URL query string, and obvious secret assignments."""
    text = EMAIL_RE.sub(REDACTED, text)
    text = PHONE_RE.sub(REDACTED, text)
    text = URL_QUERY_RE.sub(r"\1?[redacted]", text)
    text = SECRET_RE.sub(lambda m: f"{m.group(1)}={REDACTED}", text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        if record.args:
            record.args = tuple(redact(str(arg)) for arg in record.args)
        return True


def configure_logging(log_dir: Path | None = None, level: int = logging.INFO) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_dir / "gawe.log", encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
        force=True,
    )
    for handler in logging.getLogger().handlers:
        handler.addFilter(RedactingFilter())
