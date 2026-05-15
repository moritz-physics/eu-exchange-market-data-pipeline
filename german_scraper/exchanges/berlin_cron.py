"""Cron-friendly Berlin variant — same scraper, different pacing.

Subclasses :class:`german_scraper.exchanges.berlin.Berlin` and overrides
the pacing knobs so a single invocation downloads its batch and exits
cleanly (no in-process cool-down). Schedule via cron / systemd-timer /
Kubernetes ``CronJob``.
"""
from __future__ import annotations

from .berlin import Berlin
from german_scraper.settings import SETTINGS

_PACING: dict = SETTINGS.pacing("berlin-cron")


class BerlinCron(Berlin):
    """Boerse Berlin scraper sized to fit a periodic cron slot.

    Pacing comes from the ``berlin-cron`` block of ``config.json``;
    ``long_break_sec`` defaults to 0 so a single invocation exits cleanly
    and the scheduler runs it again.
    """

    name: str = "Börse Berlin (cron/batch)"
    max_files_per_run: int = int(_PACING["max_files_per_run"])
    long_break_sec: int = int(_PACING["long_break_sec"])
    post_delay: tuple[float, float] = tuple(_PACING["post_delay"])  # type: ignore[assignment]
