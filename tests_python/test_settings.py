"""Tests for the config.json loader (german_scraper.settings).

Each test builds a fresh ``Settings()`` after pointing
``$EU_SCRAPER_CONFIG`` at a fixture, so the process-wide ``SETTINGS``
singleton is never mutated.
"""
from __future__ import annotations

import json
from pathlib import Path

from german_scraper.settings import Settings


def _write(path: Path, payload) -> None:
    path.write_text(
        payload if isinstance(payload, str) else json.dumps(payload),
        encoding="utf-8",
    )


def test_repo_config_loads_and_is_consistent() -> None:
    """The committed config.json parses and exposes the expected sections."""
    s = Settings()  # picks up the repo's config.json
    assert s.default_enabled()              # non-empty
    assert s.concurrency() >= 1
    assert len(s.dq_rules()) >= 1
    assert s.pacing("berlin")["max_files_per_run"] >= 1


def test_falls_back_to_defaults_when_file_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EU_SCRAPER_CONFIG", str(tmp_path / "does-not-exist.json"))
    s = Settings()
    assert s.loaded_from is None
    assert s.default_enabled() == ["ice-post", "luxse"]
    assert s.concurrency() == 4
    assert {r["exchange"] for r in s.dq_rules()} >= {"berlin", "cboe"}


def test_malformed_config_falls_back_to_defaults(tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "config.json"
    _write(cfg, "{ this is not valid json")
    monkeypatch.setenv("EU_SCRAPER_CONFIG", str(cfg))
    s = Settings()
    assert s.loaded_from is None              # parse failed → defaults
    assert s.default_enabled() == ["ice-post", "luxse"]


def test_partial_pacing_merges_over_builtin_defaults(tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "config.json"
    _write(cfg, {"pacing": {"berlin": {"max_files_per_run": 7}}})
    monkeypatch.setenv("EU_SCRAPER_CONFIG", str(cfg))
    pacing = Settings().pacing("berlin")
    assert pacing["max_files_per_run"] == 7          # overridden
    assert pacing["long_break_sec"] == 30            # filled from default
    assert pacing["post_delay"] == [0.2, 0.6]        # filled from default


def test_explicit_overrides_are_honoured(tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "config.json"
    _write(cfg, {
        "scrape": {"default_enabled": ["cboe"], "concurrency": 9},
        "urls": {"cboe": "https://example.test/cboe"},
    })
    monkeypatch.setenv("EU_SCRAPER_CONFIG", str(cfg))
    s = Settings()
    assert s.loaded_from == str(cfg)
    assert s.default_enabled() == ["cboe"]
    assert s.concurrency() == 9
    assert s.exchange_url("cboe", "FALLBACK") == "https://example.test/cboe"


def test_exchange_url_returns_default_for_unknown_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EU_SCRAPER_CONFIG", str(tmp_path / "missing.json"))
    s = Settings()
    assert s.exchange_url("no_such_venue", "https://fallback.test") == \
        "https://fallback.test"


def test_deutsche_boerse_rows_have_a_default(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EU_SCRAPER_CONFIG", str(tmp_path / "missing.json"))
    rows = Settings().deutsche_boerse_rows()
    assert isinstance(rows, list) and rows
