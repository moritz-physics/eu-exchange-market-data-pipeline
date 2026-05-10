"""Cron-friendly Berlin variant — same scraper, different pacing.

Subclasses :class:`german_scraper.exchanges.berlin.Berlin` and overrides
the pacing knobs so a single invocation downloads its batch and exits
cleanly (no in-process cool-down). Schedule via cron / systemd-timer /
Kubernetes ``CronJob``.
"""
from __future__ import annotations

from .berlin import Berlin


class BerlinCron(Berlin):
    """Boerse Berlin scraper sized to fit a periodic cron slot."""

    name: str = "Börse Berlin (cron/batch)"
    max_files_per_run: int = 50
    long_break_sec: int = 0           # exit cleanly, scheduler runs us again
    post_delay: tuple[float, float] = (2.0, 6.0)  # politer per-file pacing
