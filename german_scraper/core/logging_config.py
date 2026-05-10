"""Centralised logging configuration for the scraper.

A single ``configure_logging`` call wires up a handler that writes to stdout
with timestamps, level, and the originating logger name. All scrapers should
obtain a logger via ``get_logger(__name__)`` and never call ``print``.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Optional

_DEFAULT_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-40s | %(message)s"
_DEFAULT_DATEFMT = "%Y-%m-%dT%H:%M:%S%z"

_configured = False


def configure_logging(level: Optional[str] = None) -> None:
    """Initialise the root logger exactly once.

    Level resolution order: explicit argument, ``LOG_LEVEL`` env var, ``INFO``.
    Safe to call repeatedly; subsequent calls are no-ops.
    """
    global _configured
    if _configured:
        return

    resolved = (level or os.environ.get("LOG_LEVEL") or "INFO").upper()
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT, datefmt=_DEFAULT_DATEFMT))

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
