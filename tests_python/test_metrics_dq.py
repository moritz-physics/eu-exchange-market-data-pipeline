"""Metrics + DQ-gate tests."""
from __future__ import annotations

import time

from german_scraper.core.dq import DQRule, check_dq
from german_scraper.core.manifest_db import BronzeRecord, Manifest
from german_scraper.core.metrics import Metrics


def test_metrics_render_prometheus_format() -> None:
    m = Metrics()
    m.inc("foo_total", description="test", x="1")
    m.inc("foo_total", description="test", x="1")
    m.inc("foo_total", description="test", x="2")
    text = m.render()
    assert "# TYPE foo_total counter" in text
    assert 'foo_total{x="1"} 2.0' in text
    assert 'foo_total{x="2"} 1.0' in text


def test_dq_min_files_rule_fires(tmp_manifest: Manifest) -> None:
    rule = DQRule("BERA", min_files=5)
    failures = check_dq(tmp_manifest, rules=(rule,), window_hours=24)
    assert failures
    assert "expected >= 5" in failures[0]


def test_dq_passes_when_volume_meets_floor(tmp_manifest: Manifest) -> None:
    now = time.time()
    for i in range(6):
        tmp_manifest.record_bronze(BronzeRecord(
            exchange="BERA", label=f"file{i}.csv",
            source_uri=f"/tmp/{i}.csv", bytes_size=1,
            sha256=f"sha{i}", scraped_at=now,
        ))
    rule = DQRule("BERA", min_files=5)
    failures = check_dq(tmp_manifest, rules=(rule,), window_hours=24)
    assert failures == []


def test_dq_failure_rate_rule_fires(tmp_manifest: Manifest) -> None:
    now = time.time()
    for i in range(10):
        tmp_manifest.record_bronze(BronzeRecord(
            exchange="BERA", label=f"file{i}.csv",
            source_uri=f"/tmp/{i}.csv", bytes_size=1,
            sha256=f"sha{i}", scraped_at=now,
        ))
    # Mark 4 of 10 as failed → 40% > 10%.
    for i in range(4):
        tmp_manifest.mark_bronze_failed(f"sha{i}", "test")
    rule = DQRule("BERA", min_files=1, max_failure_rate=0.10)
    failures = check_dq(tmp_manifest, rules=(rule,), window_hours=24)
    assert any("failure rate" in f for f in failures)
