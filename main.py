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
    }


def run_single(name: str, scrapers: dict) -> None:
    if name not in scrapers:
        logger.error("Unknown scraper '%s'. Available: %s", name, ", ".join(scrapers))
        sys.exit(1)
    scraper = scrapers[name]()
    success, fail = scraper.run()
    logger.info("Done: %d upserted, %d failed", success, fail)


def run_all(scrapers: dict) -> None:
    total_success, total_fail = 0, 0
    for name, cls in scrapers.items():
        logger.info("▶ %s", name)
        try:
            scraper = cls()
            success, fail = scraper.run()
            total_success += success
            total_fail += fail
            logger.info("  ✓ %d upserted, %d failed", success, fail)
        except Exception as e:
            logger.error("  ✗ %s crashed: %s", name, e)

    logger.info("═" * 50)
    logger.info("Total: %d upserted, %d failed", total_success, total_fail)

    # Safety net: link freshly scraped events to known venues
    # (case-insensitive) and geocode a bounded tail of stragglers —
    # unlinked events have no coordinates and are invisible on the map.
    if os.environ.get("DRY_RUN", "").lower() != "true":
        try:
            from pipeline.geocoder import run as geocode_run

            logger.info("▶ venue linking & geocoding")
            geocode_run(limit=1500)
        except Exception as e:
            logger.error("  ✗ venue linking/geocoding crashed: %s", e)


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
        run_all(scrapers)
        return

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
