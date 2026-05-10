"""Process-local Prometheus-style counters.

Lightweight on purpose: a tiny in-process counter registry that the
scraper and the ingest job emit into. Snapshot at end-of-run for ops
visibility — works in cron, k8s, and local dev unchanged.

To export to a real Prometheus / OTLP collector, point a sidecar at the
process or replace this module's backend; the call sites don't change.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from german_scraper.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class _Counter:
    name: str
    description: str
    values: dict[tuple[tuple[str, str], ...], float] = field(
        default_factory=lambda: defaultdict(float)
    )


class Metrics:
    """In-process counter / gauge registry. Thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, _Counter] = {}

    def _ensure(self, name: str, description: str) -> _Counter:
        if name not in self._counters:
            self._counters[name] = _Counter(name=name, description=description)
        return self._counters[name]

    @staticmethod
    def _key(labels: dict[str, str]) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(labels.items()))

    def inc(
        self, name: str, *, by: float = 1.0, description: str = "", **labels: str,
    ) -> None:
        """Increment a counter labelled by keyword args."""
        with self._lock:
            c = self._ensure(name, description)
            c.values[self._key(labels)] += by

    def set_gauge(
        self, name: str, value: float, *, description: str = "", **labels: str,
    ) -> None:
        """Set a gauge. Same registry; semantically a counter that can decrease."""
        with self._lock:
            c = self._ensure(name, description)
            c.values[self._key(labels)] = value

    def render(self) -> str:
        """Render in Prometheus exposition format."""
        out: list[str] = []
        with self._lock:
            for c in self._counters.values():
                if c.description:
                    out.append(f"# HELP {c.name} {c.description}")
                out.append(f"# TYPE {c.name} counter")
                for labels, value in sorted(c.values.items()):
                    label_str = (
                        "{" + ",".join(f'{k}="{v}"' for k, v in labels) + "}"
                        if labels else ""
                    )
                    out.append(f"{c.name}{label_str} {value}")
        return "\n".join(out) + ("\n" if out else "")

    def log_summary(self) -> None:
        """Log a one-line summary per counter — useful in cron logs."""
        with self._lock:
            for c in self._counters.values():
                if not c.values:
                    continue
                total = sum(c.values.values())
                logger.info("metric %s total=%g (series=%d)",
                            c.name, total, len(c.values))


# Single process-wide registry. Tests can construct a fresh ``Metrics()``.
METRICS = Metrics()


__all__ = ["METRICS", "Metrics"]
