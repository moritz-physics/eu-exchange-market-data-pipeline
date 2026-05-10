"""ICE delayed post-trade scraper — subclass of :class:`ICE`.

Same login flow and pagination logic; only the report URL, label prefix
and subdir differ.
"""
from __future__ import annotations

from .ice import ICE


class ICEPost(ICE):
    """ICE Exchange post-trade scraper."""

    name: str = "ICE Exchange (Post-Trade)"
    report_url: str = "https://www.ice.com/report/61"
    label_prefix: str = "ICE POST"
    download_subdir: str = "ice_post"
