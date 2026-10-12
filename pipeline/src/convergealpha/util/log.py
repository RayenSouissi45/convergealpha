"""Logging that can never print a secret."""

from __future__ import annotations

import logging
import sys

from convergealpha.config import secret_values

_REDACTED = "***"


def redact(text: str, secrets: list[str] | None = None) -> str:
    for value in secrets if secrets is not None else secret_values():
        text = text.replace(value, _REDACTED)
    return text


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        cleaned = redact(message)
        if cleaned != message:
            record.msg, record.args = cleaned, None
        return True


def setup(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(_RedactFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # Third-party chatter (yfinance prints one line per failed ticker) stays at WARNING.
    for noisy in ("yfinance", "urllib3", "peewee"):
        logging.getLogger(noisy).setLevel(logging.ERROR)


def get(name: str) -> logging.Logger:
    return logging.getLogger(name)
