"""
Mauerpark Flohmarkt scraper.
Iconic Sunday flea market — every Sunday, April–October.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

VENUE_NAME = "Mauerpark Flohmarkt"
VENUE_ADDRESS = "Bernauer Str. 63-64, 13355 Berlin"
VENUE_LAT = 52.5413
VENUE_LNG = 13.4020
VENUE_NEIGHBORHOOD = "Prenzlauer Berg"
SITE_URL = "https://www.mauerparkmarkt.de"


class MauerparkScraper(BaseScraper):
    source_name = "mauerpark"

    def scrape(self) -> list[dict[str, Any]]:
        # Mauerpark runs every Sunday, typically March/April–October
        # Generate schedule for the upcoming season
        dates = self._get_upcoming_sundays()
        events = []

        for d in dates:
            # Summer hours: 9:00–18:00
            events.append(
                {
                    "title": "Mauerpark Flohmarkt",
                    "venue_name": VENUE_NAME,
                    "address": VENUE_ADDRESS,
                    "lat": VENUE_LAT,
                    "lng": VENUE_LNG,
                    "neighborhood": VENUE_NEIGHBORHOOD,
                    "start_time": datetime(d.year, d.month, d.day, 9, 0).isoformat(),
                    "end_time": datetime(d.year, d.month, d.day, 18, 0).isoformat(),
                    "description": (
                        "Berlin's most famous Sunday flea market in Mauerpark. "
                        "Hundreds of stalls selling vintage clothes, records, antiques, and street food. "
                        "Karaoke bears, street performers, and a legendary Berlin atmosphere."
                    ),
                    "price": "Free",
                    "price_cents": 0,
                    "source_url": SITE_URL,
                    "source_id": f"mauerpark-{d.isoformat()}",
                    "category": "market",
                    "subcategory": "flea market",
                    "tags": [
                        "flea market",
                        "vintage",
                        "secondhand",
                        "outdoor",
                        "prenzlauer berg",
                        "free entry",
                        "family-friendly",
                    ],
                    "source_tags": [],
                    "source": self.source_name,
                }
            )

        logger.info("mauerpark: generated %d dates", len(events))
        return events

    def _get_upcoming_sundays(self, weeks: int = 20) -> list[date]:
        today = date.today()
        days_until_sunday = (6 - today.weekday()) % 7
        next_sunday = today + timedelta(days=days_until_sunday)

        sundays = []
        for i in range(weeks):
            d = next_sunday + timedelta(weeks=i)
            # Only include April–October (outdoor market season)
            if 4 <= d.month <= 10:
                sundays.append(d)

        return sundays
