"""Command-line entry point for the EU exchange scraper.

Edit the ``SCRAPERS`` list to enable/disable individual exchanges. The
default ``DEBUG_MODE`` of ``True`` prevents any download or write — use it
for dry runs, set to ``False`` for production.
"""
from __future__ import annotations

import asyncio
from typing import Type

from german_scraper.core.logging_config import configure_logging, get_logger
from german_scraper.core.playwright_client import PlaywrightClient
from german_scraper.exchanges.athex import ATHEX
from german_scraper.exchanges.bank_of_greece import BankOfGreece
from german_scraper.exchanges.base import Exchange
from german_scraper.exchanges.berlin import Berlin
from german_scraper.exchanges.berlin_cron import BerlinCron
from german_scraper.exchanges.bme import BME
from german_scraper.exchanges.boersenag import BoersenAG
from german_scraper.exchanges.bratislava import Bratislava
from german_scraper.exchanges.bucharest import Bucharest
from german_scraper.exchanges.cboe import Cboe
from german_scraper.exchanges.ice import ICE
from german_scraper.exchanges.ice_post import ICEPost
from german_scraper.exchanges.lsx import LSX
from german_scraper.exchanges.luxse import LuxSE
from german_scraper.exchanges.munich import Munich
from german_scraper.exchanges.wienerboerse import WienerBoerse
from german_scraper.exchanges.wienerboerse_stealth import WienerBoerseStealth
from german_scraper.pipelines.save_local import SaveLocalPipeline

# Toggle exchanges here. Comments preserve the original "what works / what is
# unstable" notes from the research project.
SCRAPERS: list[Type[Exchange]] = [
    # BME,                  # Spain post-trade JSON
    # Cboe,                 # Cboe Europe hourly RTS-13 CSVs
    # BankOfGreece,         # HDAT pre/post-trade JSON
    # Bucharest,            # BVB Pre + Post quick downloads
    # ATHEX,                # AAPA + ATHEX pre/post CSVs
    # BoersenAG,            # Düsseldorf/Hamburg/Hannover MiFID II
    # Berlin,               # Boerse Berlin (works well; tighten robustness)
    # LSX,                  # Lang & Schwarz pretrade
    # Munich,               # gettex (Munich) — large files
    # WienerBoerse,         # Unstable due to reCAPTCHA
    # ICE,                  # Pre-trade — interactive 2FA prompt
    # BerlinCron,           # Cron-friendly Berlin variant
    ICEPost,                # Post-trade — interactive 2FA prompt
    LuxSE,                  # Form + email-link delivery
    # Bratislava,           # Form + email-attachment delivery (still flaky)
    # WienerBoerseStealth,  # Wiener Börse with playwright-stealth
]


async def main(debug: bool = True) -> None:
    """Run every enabled scraper in sequence, isolating per-scraper failures."""
    configure_logging()
    logger = get_logger("scraper.cli")

    pipeline = SaveLocalPipeline()
    async with PlaywrightClient().launch() as browser:
        for cls in SCRAPERS:
            scraper = cls(browser, pipeline, debug=debug)
            logger.info("=== %s ===", scraper.name)
            try:
                await scraper.run()
            except Exception as exc:
                logger.exception("%s failed: %s", scraper.name, exc)


if __name__ == "__main__":
    # Set debug=False to actually download.
    asyncio.run(main(debug=True))
