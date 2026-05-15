"""Scraper-registry contract tests.

Covers the registry as a whole plus the two scrapers ported from the
legacy TypeScript prototypes: Borsa Bulgaria and Deutsche Börse.
Construction is I/O-free (``Exchange.__init__`` only stores references
and builds a logger), so no browser or network is needed.
"""
from __future__ import annotations

import pytest

from german_scraper.cli import SCRAPER_REGISTRY
from german_scraper.exchanges.base import Exchange

NEWLY_PORTED = ("bulgaria", "deutsche-boerse")


def test_newly_ported_scrapers_are_registered() -> None:
    for key in NEWLY_PORTED:
        assert key in SCRAPER_REGISTRY, f"{key} missing from SCRAPER_REGISTRY"


@pytest.mark.parametrize("key", sorted(SCRAPER_REGISTRY))
def test_registry_entry_is_a_usable_exchange(key: str) -> None:
    cls = SCRAPER_REGISTRY[key]
    assert issubclass(cls, Exchange)
    # run() must be implemented (not the abstract base method).
    assert cls.run is not Exchange.run, f"{key} does not override run()"
    # Construction touches no browser / network.
    inst = cls(browser=None, pipeline=None, debug=True)  # type: ignore[arg-type]
    assert isinstance(inst.name, str) and inst.name
    assert inst.name != "Unnamed Exchange", f"{key} did not set a name"


def test_bulgaria_scraper_basics() -> None:
    from german_scraper.exchanges.bulgaria import BSE_URL, BorsaBulgaria
    assert BSE_URL.startswith("http")
    inst = BorsaBulgaria(browser=None, pipeline=None, debug=True)  # type: ignore[arg-type]
    assert "Bulgaria" in inst.name


def test_deutsche_boerse_scraper_basics() -> None:
    from german_scraper.exchanges.deutsche_boerse import BASE_URL, DeutscheBoerse
    assert BASE_URL.startswith("http")
    inst = DeutscheBoerse(browser=None, pipeline=None, debug=True)  # type: ignore[arg-type]
    assert "Deutsche Börse" in inst.name
    assert inst.download_subdir == "deutsche-boerse"
