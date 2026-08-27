#!/usr/bin/env python3
"""
NachtKarte Berlin — Event Scraping Pipeline
Usage:
    python main.py                    # start scheduler (runs continuously)
    python main.py --run-all          # run all scrapers once and exit
    python main.py --run kulturdaten  # run a specific scraper once
    python main.py --dry-run          # run all scrapers but don't write to DB
"""

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("nachtkarte")


# ── Scraper registry ──────────────────────────────────────────────────────────
def get_scrapers() -> dict:
    from scrapers.berlin_de import BerlinDeScraper
    from scrapers.berlinmitkind import BerlinMitKindScraper
    from scrapers.discovery_staging import DiscoveryStagingScraper
    from scrapers.eventbrite import EventbriteScraper
    from scrapers.kulturdaten import KulturdatenScraper
    from scrapers.luma import LumaScraper
    from scrapers.meetup import MeetupScraper
    from scrapers.planetarium import PlanetariumScraper
    from scrapers.rausgegangen import RausgegangeScraper
    from scrapers.resident_advisor import ResidentAdvisorScraper
    from scrapers.startbahn import StartbahnScraper
    from scrapers.tip_berlin import TipBerlinScraper
    from scrapers.venues.feine_klingen import FeineKlingenScraper
    from scrapers.venues.froschkoenig import FroschkoenigScraper
    from scrapers.venues.generic_website import GenericWebsiteScraper
    from scrapers.venues.holzmarkt import HolzmarktScraper
    from scrapers.venues.huxleys import HuxleysScraper
    from scrapers.venues.instagram_events import InstagramEventsScraper
    from scrapers.venues.jazzclubs import JazzclubsScraper
    from scrapers.venues.klunkerkranich import KlunkerkranichScraper
    from scrapers.venues.markthalle_neun import MarkthalleScraper
    from scrapers.venues.mauerpark import MauerparkScraper
    from scrapers.venues.nowkoelln import NowkoellnScraper
    from scrapers.venues.themakery import TheMakeryScraper
    from scrapers.venues.wochenmaerkte import WochenmaerkteScraper

    return {
        "kulturdaten": KulturdatenScraper,
        "eventbrite": EventbriteScraper,
        "luma": LumaScraper,
        "meetup": MeetupScraper,
        "rausgegangen": RausgegangeScraper,
        "tip_berlin": TipBerlinScraper,
        "berlin_de": BerlinDeScraper,
        "resident_advisor": ResidentAdvisorScraper,
        "markthalle_neun": MarkthalleScraper,
        "klunkerkranich": KlunkerkranichScraper,
        "holzmarkt": HolzmarktScraper,
        "nowkoelln": NowkoellnScraper,
        "mauerpark": MauerparkScraper,
        "wochenmaerkte": WochenmaerkteScraper,
        "jazzity": JazzclubsScraper,
        "planetarium": PlanetariumScraper,
        "berlinmitkind": BerlinMitKindScraper,
        "startbahn": StartbahnScraper,
        "feine_klingen": FeineKlingenScraper,
        "froschkoenig": FroschkoenigScraper,
        "huxleys": HuxleysScraper,
        "themakery": TheMakeryScraper,
        "venue_website": GenericWebsiteScraper,
        "instagram": InstagramEventsScraper,
        # Events found by the discovery agent (separate repo), staged in
        # `discovered_events`. Reads a table, never the agent's code.
        "discovery_agent": DiscoveryStagingScraper,
    }


def run_single(name: str, scrapers: dict) -> None:
    if name not in scrapers:
        logger.error("Unknown scraper '%s'. Available: %s", name, ", ".join(scrapers))
        sys.exit(1)
    scraper = scrapers[name]()
    outcome = scraper.run()
    if outcome.crashed:
        logger.error("Done: %s FAILED — %s", name, outcome.error)
        sys.exit(1)
    logger.info("Done: %d upserted, %d failed", outcome.upserted, outcome.rows_failed)


def run_all(scrapers: dict) -> list[str]:
    """Run every scraper. Returns the names of the sources that FAILED.

    A crashing source used to be logged and forgotten: it contributed nothing to
    `total_fail`, so the summary line said "0 failed" no matter how many died.
    That is how `venue_website` and `instagram` produced zero rows for months
    without anyone noticing. Failures are counted and returned now, and the
    summary reports them separately from individual rows that failed to upsert.
    """
    total_success, total_rows_failed = 0, 0
    failed_sources: list[str] = []
    for name, cls in scrapers.items():
        logger.info("▶ %s", name)
        try:
            outcome = cls().run()
        except Exception as e:  # noqa: BLE001 — one bad source never stops the rest
            logger.error("  ✗ %s crashed: %s", name, e)
            failed_sources.append(name)
            continue
        if outcome.crashed:
            logger.error("  ✗ %s failed: %s", name, outcome.error)
            failed_sources.append(name)
            continue
        total_success += outcome.upserted
        total_rows_failed += outcome.rows_failed
        logger.info("  ✓ %d upserted, %d failed", outcome.upserted, outcome.rows_failed)

    logger.info("═" * 50)
    # Keep the wording of this line stable: deploy/run-scrape.sh parses it to
    # decide whether a nightly run counts as ok, degraded or broken.
    logger.info(
        "Total: %d upserted, %d failed, %d source(s) failed%s",
        total_success,
        total_rows_failed,
        len(failed_sources),
        f" ({', '.join(failed_sources)})" if failed_sources else "",
    )
    # Safety net: link freshly scraped events to known venues
    # (case-insensitive) and geocode a bounded tail of stragglers —
    # unlinked events have no coordinates and are invisible on the map.
    #
    # This runs AFTER the summary and BEFORE the return, deliberately. An earlier
    # version of this function returned above it and made the whole block dead
    # code: every nightly run would have skipped venue linking and geocoding, and
    # newly scraped events would have been invisible on the map. It failed
    # silently — the six tests around this function all still passed, because
    # they only ever asserted on the return value.
    #
    # It also runs regardless of how many sources failed: the events that DID
    # arrive still need coordinates.
    if os.environ.get("DRY_RUN", "").lower() != "true":
        try:
            from pipeline.geocoder import run as geocode_run

            logger.info("▶ venue linking & geocoding")
            geocode_run(limit=1500)
        except Exception as e:
            logger.error("  ✗ venue linking/geocoding crashed: %s", e)

    return failed_sources


def main():
    parser = argparse.ArgumentParser(description="NachtKarte event scraping pipeline")
    parser.add_argument("--run-all", action="store_true", help="Run all scrapers once and exit")
    parser.add_argument("--run", metavar="SCRAPER", help="Run a specific scraper and exit")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    parser.add_argument("--list", action="store_true", help="List available scrapers")
    args = parser.parse_args()

    if args.dry_run:
        os.environ["DRY_RUN"] = "true"
        logger.info("DRY RUN mode — no DB writes")

    scrapers = get_scrapers()

    if args.list:
        print("Available scrapers:")
        for name in scrapers:
            print(f"  {name}")
        return

    if args.run:
        run_single(args.run, scrapers)
        return

    if args.run_all:
        failed_sources = run_all(scrapers)
        # Hard exit: lingering non-daemon threads (playwright/scheduler imports) kept
        # the process alive until the CI timeout killed it — nightly runs showed
        # 'INFO done' followed by an orphaned python process and a cancelled job.
        logging.shutdown()
        # The hard exit stays: lingering non-daemon threads (playwright/scheduler
        # imports) kept the process alive until CI killed it. But it now carries
        # the verdict — os._exit(0) meant a run could never report failure at all.
        os._exit(1 if failed_sources else 0)

    # Default: start the scheduler
    logger.info("Starting NachtKarte pipeline scheduler...")
    from pipeline.scheduler import build_scheduler

    scheduler = build_scheduler()

    try:
        logger.info("Scheduler running. Jobs:")
        for job in scheduler.get_jobs():
            logger.info("  %s → %s", job.name, job.next_run_time)
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
