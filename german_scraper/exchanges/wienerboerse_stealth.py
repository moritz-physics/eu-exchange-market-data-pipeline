"""Wiener Börse stealth variant — same scraper, ``stealth=True``."""
from __future__ import annotations

from .wienerboerse import WienerBoerse


class WienerBoerseStealth(WienerBoerse):
    """Wiener Börse pre-trade scraper with playwright-stealth + human pacing."""

    name: str = "Wiener Börse (stealth)"
    stealth: bool = True
