"""
APScheduler-based cron scheduler for the NachtKarte pipeline.
Each scraper runs on its own schedule.
"""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


def run_scraper(scraper_class, label: str):
    """Instantiate and run a scraper, log results."""
    logger.info("▶ Running scraper: %s", label)
    try:
        scraper = scraper_class()
        success, fail = scraper.run()
        logger.info("✓ %s: %d upserted, %d failed", label, success, fail)
    except Exception as e:
        logger.error("✗ %s crashed: %s", label, e)


def run_db_cleanup():
    """Nightly maintenance: normalize taxonomy strays, deactivate past events."""
    logger.info("▶ Running DB cleanup")
    try:
        from scripts.db_cleanup import run
        run(dry_run=False)
        logger.info("✓ DB cleanup done")
    except Exception as e:
        logger.error("✗ DB cleanup crashed: %s", e)


def build_scheduler() -> BlockingScheduler:
    from scrapers.berlin_de import BerlinDeScraper
    from scrapers.eventbrite import EventbriteScraper
    from scrapers.kulturdaten import KulturdatenScraper
    from scrapers.meetup import MeetupScraper
    from scrapers.rausgegangen import RausgegangeScraper
    from scrapers.resident_advisor import ResidentAdvisorScraper
    from scrapers.tip_berlin import TipBerlinScraper
    from scrapers.venues.holzmarkt import HolzmarktScraper
    from scrapers.venues.klunkerkranich import KlunkerkranichScraper
    from scrapers.venues.markthalle_neun import MarkthalleScraper
    from scrapers.venues.mauerpark import MauerparkScraper
    from scrapers.venues.nowkoelln import NowkoellnScraper
    from scrapers.venues.jazzclubs import JazzclubsScraper
    from scrapers.venues.wochenmaerkte import WochenmaerkteScraper
    from scrapers.luma import LumaScraper
    from scrapers.planetarium import PlanetariumScraper
    from scrapers.berlinmitkind import BerlinMitKindScraper
    from scrapers.startbahn import StartbahnScraper
    from scrapers.venues.feine_klingen import FeineKlingenScraper
    from scrapers.venues.froschkoenig import FroschkoenigScraper
    from scrapers.venues.huxleys import HuxleysScraper
    from scrapers.bandsintown import BandsintownScraper

    scheduler = BlockingScheduler(timezone="Europe/Berlin")

    # ── Tier 1: APIs — daily at 6:00 AM Berlin time ────────────────────────────
    for cls, label in [
        (KulturdatenScraper, "kulturdaten"),
        (EventbriteScraper, "eventbrite"),
        (MeetupScraper, "meetup"),
        (LumaScraper, "luma"),
        (BandsintownScraper, "bandsintown"),
    ]:
        scheduler.add_job(
            run_scraper,
            CronTrigger(hour=6, minute=0),
            args=[cls, label],
            id=label,
            name=f"Tier1:{label}",
            replace_existing=True,
        )

    # ── Tier 2: HTML scrapers — daily at 6:30 AM ──────────────────────────────
    for cls, label in [
        (TipBerlinScraper, "tip_berlin"),
        (BerlinDeScraper, "berlin_de"),
        (BerlinMitKindScraper, "berlinmitkind"),
    ]:
        scheduler.add_job(
            run_scraper,
            CronTrigger(hour=6, minute=30),
            args=[cls, label],
            id=label,
            replace_existing=True,
        )

    # Rausgegangen: 2x/day — 8 AM and 6 PM (picks get updated throughout day)
    scheduler.add_job(
        run_scraper,
        CronTrigger(hour="8,18", minute=0),
        args=[RausgegangeScraper, "rausgegangen"],
        id="rausgegangen",
        replace_existing=True,
    )

    # Resident Advisor: daily at 3:00 AM (off-peak, less blocking)
    scheduler.add_job(
        run_scraper,
        CronTrigger(hour=3, minute=0),
        args=[ResidentAdvisorScraper, "resident_advisor"],
        id="resident_advisor",
        replace_existing=True,
    )

    # ── Tier 3: Venue scrapers — daily at 7:00 AM ─────────────────────────────
    for cls, label in [
        (MarkthalleScraper, "markthalle_neun"),
        (KlunkerkranichScraper, "klunkerkranich"),
        (HolzmarktScraper, "holzmarkt"),
        (NowkoellnScraper, "nowkoelln"),
        (MauerparkScraper, "mauerpark"),
        (JazzclubsScraper, "jazzity"),
        (WochenmaerkteScraper, "wochenmaerkte"),
        (PlanetariumScraper, "planetarium"),
        (StartbahnScraper, "startbahn"),
        (FeineKlingenScraper, "feine_klingen"),
        (FroschkoenigScraper, "froschkoenig"),
        (HuxleysScraper, "huxleys"),
    ]:
        scheduler.add_job(
            run_scraper,
            CronTrigger(hour=7, minute=0),
            args=[cls, label],
            id=label,
            replace_existing=True,
        )

    # ── Maintenance: nightly cleanup at 5:00 AM (after the 3 AM RA run,
    # before the 6 AM API scrapes) ────────────────────────────────────────────
    scheduler.add_job(
        run_db_cleanup,
        CronTrigger(hour=5, minute=0),
        id="db_cleanup",
        name="Maintenance:db_cleanup",
        replace_existing=True,
    )

    return scheduler
