"""Central runtime configuration loaded from ``config.json``.

Single source of truth for tunables that used to be scattered as module
constants: the default scraper set, concurrency, per-venue pacing, DQ
thresholds, and venue URLs.

Resilience by design
====================

Every accessor falls back to a built-in default, so a missing, partial,
or malformed ``config.json`` never breaks the pipeline — it just runs
with the historical hard-coded values.

The config file is resolved, in order:

  1. ``$EU_SCRAPER_CONFIG`` (explicit path)
  2. ``config.json`` next to the repo root

Not to be confused with :mod:`german_scraper.storage.config`, which
resolves *storage backend* settings from environment variables.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from german_scraper.core.logging_config import get_logger

logger = get_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config.json"

# ── Built-in fallbacks — used when config.json (or a key) is absent ──────
_DEFAULT_ENABLED: list[str] = ["ice-post", "luxse"]
_DEFAULT_CONCURRENCY: int = 4

_DEFAULT_PACING: dict[str, dict[str, Any]] = {
    "berlin":      {"max_files_per_run": 50, "long_break_sec": 30, "post_delay": [0.2, 0.6]},
    "berlin-cron": {"max_files_per_run": 50, "long_break_sec": 0,  "post_delay": [2.0, 6.0]},
}

_DEFAULT_DQ_RULES: list[dict[str, Any]] = [
    {"exchange": "berlin",         "min_files": 20, "max_failure_rate": 0.10},
    {"exchange": "cboe",           "min_files": 20, "max_failure_rate": 0.10},
    {"exchange": "athex",          "min_files": 3,  "max_failure_rate": 0.10},
    {"exchange": "bme",            "min_files": 1,  "max_failure_rate": 0.20},
    {"exchange": "bank-of-greece", "min_files": 1,  "max_failure_rate": 0.20},
]

_DEFAULT_DB_ROWS: list[str] = ["Xetra – Pre-Trade File service"]


class Settings:
    """Lazily-parsed view over ``config.json`` with hard-coded fallbacks."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self.loaded_from: str | None = None
        self.reload()

    def reload(self) -> None:
        """Re-read the config file. Safe to call repeatedly (e.g. in tests)."""
        path = Path(os.environ.get("EU_SCRAPER_CONFIG") or _DEFAULT_CONFIG_PATH)
        if not path.is_file():
            logger.info("No config file at %s — using built-in defaults", path)
            self._data, self.loaded_from = {}, None
            return
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read config %s (%s) — using defaults", path, exc)
            self._data, self.loaded_from = {}, None
            return
        if not isinstance(parsed, dict):
            logger.warning("Config %s is not a JSON object — using defaults", path)
            self._data, self.loaded_from = {}, None
            return
        self._data, self.loaded_from = parsed, str(path)
        logger.info("Loaded config from %s", path)

    # ── scrape ──────────────────────────────────────────────────────────
    def default_enabled(self) -> list[str]:
        """Scrapers run when ``--exchanges`` is not passed."""
        scrape = self._data.get("scrape") or {}
        value = scrape.get("default_enabled")
        return list(value) if value else list(_DEFAULT_ENABLED)

    def concurrency(self) -> int:
        """Default max parallel scrapers."""
        scrape = self._data.get("scrape") or {}
        try:
            return int(scrape.get("concurrency") or _DEFAULT_CONCURRENCY)
        except (TypeError, ValueError):
            return _DEFAULT_CONCURRENCY

    # ── pacing ──────────────────────────────────────────────────────────
    def pacing(self, name: str) -> dict[str, Any]:
        """Per-venue pacing knobs, merged over the built-in defaults."""
        base = dict(_DEFAULT_PACING.get(name, {}))
        configured = (self._data.get("pacing") or {}).get(name) or {}
        base.update(configured)
        return base

    # ── data quality ────────────────────────────────────────────────────
    def dq_rules(self) -> list[dict[str, Any]]:
        """Raw DQ-rule dicts; :mod:`german_scraper.core.dq` builds ``DQRule``s."""
        rules = self._data.get("dq_rules")
        return list(rules) if rules else list(_DEFAULT_DQ_RULES)

    # ── urls ────────────────────────────────────────────────────────────
    def exchange_url(self, key: str, default: str) -> str:
        """Return the configured URL for ``key``, or ``default`` if unset.

        ``default`` is the historical hard-coded literal in each scraper,
        so URLs keep working even with no ``urls`` section in the config.
        """
        return (self._data.get("urls") or {}).get(key) or default

    # ── deutsche börse ──────────────────────────────────────────────────
    def deutsche_boerse_rows(self) -> list[str]:
        """Row labels whose popup pages the Deutsche Börse scraper visits."""
        db = self._data.get("deutsche_boerse") or {}
        rows = db.get("rows")
        return list(rows) if rows else list(_DEFAULT_DB_ROWS)


# Process-wide singleton. Tests can call ``SETTINGS.reload()`` after
# pointing ``$EU_SCRAPER_CONFIG`` at a fixture.
SETTINGS = Settings()


__all__ = ["SETTINGS", "Settings"]
