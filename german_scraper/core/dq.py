"""Data-quality gates.

Per-venue expectations that must hold for a run to be considered
healthy. The baseline expectation is "we got at least N rows for the
expected exchanges within the last K hours". A run that produces zero
rows for an exchange that is normally chatty is the most common silent
failure mode in scraping pipelines and the one most worth catching.

Usage:
    from german_scraper.core.dq import check_dq, DEFAULT_RULES
    failures = check_dq(manifest, rules=DEFAULT_RULES, window_hours=24)
    if failures:
        sys.exit(1)
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable

from german_scraper.core.logging_config import get_logger
from german_scraper.core.manifest_db import Manifest

logger = get_logger(__name__)


@dataclass(frozen=True)
class DQRule:
    """One expectation for one exchange / data-type.

    ``min_files`` is the minimum number of bronze files we expect to see
    in ``window_hours``. ``max_failure_rate`` is the maximum acceptable
    fraction of bronze rows in ``FAILED`` state.
    """

    exchange: str            # substring match on bronze.exchange
    min_files: int = 0
    max_failure_rate: float = 0.10


# Calibrate to typical observed daily volumes. Update from prod stats.
DEFAULT_RULES: tuple[DQRule, ...] = (
    DQRule("berlin",         min_files=20, max_failure_rate=0.10),
    DQRule("cboe",           min_files=20, max_failure_rate=0.10),
    DQRule("athex",          min_files=3,  max_failure_rate=0.10),
    DQRule("bme",            min_files=1,  max_failure_rate=0.20),
    DQRule("bank-of-greece", min_files=1,  max_failure_rate=0.20),
)


def check_dq(
    manifest: Manifest,
    *,
    rules: Iterable[DQRule] = DEFAULT_RULES,
    window_hours: float = 24.0,
) -> list[str]:
    """Evaluate ``rules`` against the manifest. Returns the list of failures.

    Empty list means everything is healthy. Each failure is a short
    human-readable string suitable for paging.
    """
    cutoff = time.time() - window_hours * 3600
    failures: list[str] = []
    with manifest._conn() as conn:  # type: ignore[attr-defined]
        for rule in rules:
            row = conn.execute(
                """SELECT
                    SUM(CASE WHEN status='downloaded' THEN 1 ELSE 0 END) AS dl,
                    SUM(CASE WHEN status='ingested'   THEN 1 ELSE 0 END) AS ing,
                    SUM(CASE WHEN status='failed'     THEN 1 ELSE 0 END) AS fail
                   FROM bronze
                   WHERE scraped_at >= ? AND exchange LIKE ?""",
                (cutoff, f"%{rule.exchange}%"),
            ).fetchone()
            dl  = row["dl"]   or 0
            ing = row["ing"]  or 0
            fail = row["fail"] or 0
            total = dl + ing + fail
            if total < rule.min_files:
                failures.append(
                    f"DQ: exchange={rule.exchange} got {total} files in last "
                    f"{window_hours:g}h (expected >= {rule.min_files})"
                )
            elif total > 0 and fail / total > rule.max_failure_rate:
                failures.append(
                    f"DQ: exchange={rule.exchange} failure rate "
                    f"{fail}/{total}={fail/total:.0%} exceeds "
                    f"max={rule.max_failure_rate:.0%}"
                )
    if failures:
        for f in failures:
            logger.error("%s", f)
    else:
        logger.info("DQ checks passed (%d rules, %.1fh window)", len(list(rules)), window_hours)
    return failures


__all__ = ["DEFAULT_RULES", "DQRule", "check_dq"]
