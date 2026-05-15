"""Typer-based CLI for the EU exchange data pipeline.

Subcommands
===========

    eu-scraper scrape          – run scrapers (concurrent, per-context)
    eu-scraper ingest          – bronze → silver
    eu-scraper dq              – run data-quality gates against the manifest
    eu-scraper manifest-stats  – print bronze/silver counts by status
    eu-scraper metrics         – render the in-process metric registry
    eu-scraper demo            – run the dry-run demo for the storage layer

Each subcommand picks up env vars (``DRY_RUN``, ``STORAGE_BACKEND``,
``MANIFEST_DSN``, ``CONCURRENCY``, …) so the same invocation works on
laptop, server, and Kubernetes unchanged.
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional, Type

import typer

from german_scraper.core.logging_config import configure_logging, get_logger
from german_scraper.core.metrics import METRICS
from german_scraper.core.playwright_client import PlaywrightClient
from german_scraper.settings import SETTINGS
from german_scraper.exchanges.athex import ATHEX
from german_scraper.exchanges.bank_of_greece import BankOfGreece
from german_scraper.exchanges.base import Exchange
from german_scraper.exchanges.berlin import Berlin
from german_scraper.exchanges.berlin_cron import BerlinCron
from german_scraper.exchanges.bme import BME
from german_scraper.exchanges.boersenag import BoersenAG
from german_scraper.exchanges.bratislava import Bratislava
from german_scraper.exchanges.bucharest import Bucharest
from german_scraper.exchanges.bulgaria import BorsaBulgaria
from german_scraper.exchanges.cboe import Cboe
from german_scraper.exchanges.deutsche_boerse import DeutscheBoerse
from german_scraper.exchanges.ice import ICE
from german_scraper.exchanges.ice_post import ICEPost
from german_scraper.exchanges.lsx import LSX
from german_scraper.exchanges.luxse import LuxSE
from german_scraper.exchanges.munich import Munich
from german_scraper.exchanges.wienerboerse import WienerBoerse
from german_scraper.exchanges.wienerboerse_stealth import WienerBoerseStealth
from german_scraper.pipelines.save_local import SaveLocalPipeline


SCRAPER_REGISTRY: dict[str, Type[Exchange]] = {
    "athex": ATHEX,
    "bank-of-greece": BankOfGreece,
    "berlin": Berlin,
    "berlin-cron": BerlinCron,
    "bme": BME,
    "boersenag": BoersenAG,
    "bratislava": Bratislava,
    "bucharest": Bucharest,
    "bulgaria": BorsaBulgaria,
    "cboe": Cboe,
    "deutsche-boerse": DeutscheBoerse,
    "ice": ICE,
    "ice-post": ICEPost,
    "lsx": LSX,
    "luxse": LuxSE,
    "munich": Munich,
    "wienerboerse": WienerBoerse,
    "wienerboerse-stealth": WienerBoerseStealth,
}

DEFAULT_ENABLED: list[str] = SETTINGS.default_enabled()

app = typer.Typer(
    add_completion=False,
    help="EU exchange pre & post-trade data acquisition pipeline.",
    no_args_is_help=True,
)


# ── scrape ──────────────────────────────────────────────────────────────
async def _run_one(
    cls: Type[Exchange], browser, pipeline: SaveLocalPipeline,
    debug: bool, semaphore: asyncio.Semaphore, logger,
) -> None:
    async with semaphore:
        context = await browser.new_context()
        try:
            scraper = cls(context, pipeline, debug=debug)
            logger.info("=== %s ===", scraper.name)
            await scraper.run()
        except Exception as exc:
            logger.exception("%s failed: %s", cls.__name__, exc)
        finally:
            await context.close()


async def _scrape_async(
    enabled: list[str], debug: bool, concurrency: int,
) -> None:
    configure_logging()
    logger = get_logger("scraper.cli")
    selected: list[Type[Exchange]] = []
    for key in enabled:
        cls = SCRAPER_REGISTRY.get(key)
        if cls is None:
            logger.error("Unknown exchange %r — known: %s",
                         key, sorted(SCRAPER_REGISTRY))
            continue
        selected.append(cls)
    if not selected:
        logger.warning("No scrapers enabled; nothing to do")
        return
    pipeline = SaveLocalPipeline()
    semaphore = asyncio.Semaphore(concurrency)
    async with PlaywrightClient().launch() as browser:
        logger.info("Running %d scrapers with concurrency=%d",
                    len(selected), concurrency)
        await asyncio.gather(*(
            _run_one(cls, browser, pipeline, debug, semaphore, logger)
            for cls in selected
        ))
    METRICS.log_summary()


@app.command()
def scrape(
    exchanges: Optional[str] = typer.Option(
        None, "--exchanges", "-e",
        help=("Comma-separated list. Default: " + ",".join(DEFAULT_ENABLED) +
              ". Known: " + ",".join(sorted(SCRAPER_REGISTRY))),
    ),
    concurrency: int = typer.Option(
        int(os.environ.get("CONCURRENCY", str(SETTINGS.concurrency()))),
        "--concurrency", "-c",
        help="Max parallel scrapers",
    ),
    no_debug: bool = typer.Option(
        False, "--no-debug",
        help="Disable dry-run / debug mode and actually download",
    ),
) -> None:
    """Run scrapers concurrently with cookie-isolated contexts."""
    enabled = exchanges.split(",") if exchanges else DEFAULT_ENABLED
    asyncio.run(_scrape_async(enabled, debug=not no_debug, concurrency=concurrency))


# ── ingest ──────────────────────────────────────────────────────────────
@app.command()
def ingest(
    exchange: Optional[str] = typer.Option(
        None, "--exchange", "-e",
        help="Restrict to bronze rows whose exchange contains this substring",
    ),
    limit: int = typer.Option(1000, help="Maximum bronze rows to process"),
) -> None:
    """Process pending bronze payloads into the silver Parquet dataset."""
    configure_logging()
    from german_scraper.storage.ingest import run_ingest
    stats = run_ingest(exchange=exchange, limit=limit)
    typer.echo(f"ingest: {stats}")
    METRICS.log_summary()


# ── dq ──────────────────────────────────────────────────────────────────
@app.command()
def dq(
    window_hours: float = typer.Option(24.0, help="Lookback window in hours"),
) -> None:
    """Evaluate data-quality rules. Exits non-zero on any failure."""
    configure_logging()
    from german_scraper.core.dq import check_dq
    from german_scraper.core.manifest_db import DEFAULT_MANIFEST_PATH, Manifest
    failures = check_dq(
        Manifest(os.environ.get("MANIFEST_DSN", str(DEFAULT_MANIFEST_PATH))),
        window_hours=window_hours,
    )
    if failures:
        for f in failures:
            typer.echo(f, err=True)
        raise typer.Exit(code=1)
    typer.echo("dq: all rules passed")


# ── manifest-stats ──────────────────────────────────────────────────────
@app.command("manifest-stats")
def manifest_stats() -> None:
    """Print bronze/silver counts by status from the SQLite manifest."""
    configure_logging()
    from german_scraper.core.manifest_db import DEFAULT_MANIFEST_PATH, Manifest
    m = Manifest(os.environ.get("MANIFEST_DSN", str(DEFAULT_MANIFEST_PATH)))
    stats = m.stats()
    typer.echo(f"bronze: {stats['bronze']}")
    typer.echo(f"silver: {stats['silver']}")


# ── metrics ─────────────────────────────────────────────────────────────
@app.command()
def metrics() -> None:
    """Render the in-process metrics registry in Prometheus format."""
    configure_logging()
    typer.echo(METRICS.render() or "# (no metrics emitted in this process)")


# ── demo ────────────────────────────────────────────────────────────────
@app.command()
def demo() -> None:
    """Run the storage-layer dry-run demo (synthetic records, no I/O)."""
    os.environ["DRY_RUN"] = "true"
    from german_scraper.storage.dry_run_demo import main
    main()


def app_main() -> None:
    """Console-script entrypoint registered in ``[project.scripts]``."""
    app()


if __name__ == "__main__":
    app_main()
