"""Centralised logging configuration.

When stdout is a TTY (developer running locally) we use a human-readable
text formatter. Otherwise (cron / k8s / docker logs) we emit JSON Lines —
one JSON object per log record, ready to ship to ELK / Loki / Datadog
with no further parsing.

The output format is selectable via env: ``LOG_FORMAT=json|text``. The
default ``auto`` picks JSON when stdout is not a TTY.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional

_DEFAULT_TEXT_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-40s | %(message)s"
_DEFAULT_DATEFMT = "%Y-%m-%dT%H:%M:%S%z"

_configured = False


class _JSONFormatter(logging.Formatter):
    """One-line JSON record per log entry, UTC ISO timestamps."""

    _SKIP = {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "message", "module",
        "msecs", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName",
        "taskName", "getMessage",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info
        # Forward any user-injected fields (logger.info(..., extra={...})).
        for key, value in record.__dict__.items():
            if key in self._SKIP or key.startswith("_"):
                continue
            try:
                json.dumps(value)
            except TypeError:
                value = repr(value)
            payload[key] = value
        return json.dumps(payload, default=str, separators=(",", ":"))


def _resolve_format() -> str:
    """Honour LOG_FORMAT, defaulting to JSON when stdout is not a TTY."""
    raw = (os.environ.get("LOG_FORMAT") or "auto").lower()
    if raw == "json":
        return "json"
    if raw == "text":
        return "text"
    return "text" if sys.stdout.isatty() else "json"


def configure_logging(level: Optional[str] = None) -> None:
    """Initialise the root logger exactly once. Safe to call repeatedly."""
    global _configured
    if _configured:
        return

    resolved = (level or os.environ.get("LOG_LEVEL") or "INFO").upper()
    fmt = _resolve_format()

    handler = logging.StreamHandler(stream=sys.stdout)
    if fmt == "json":
        handler.setFormatter(_JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(_DEFAULT_TEXT_FORMAT, datefmt=_DEFAULT_DATEFMT))

    root = logging.getLogger()
    root.setLevel(resolved)
    root.handlers = [handler]

    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger; calls ``configure_logging`` lazily."""
    if not _configured:
        configure_logging()
    return logging.getLogger(name)
