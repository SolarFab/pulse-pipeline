"""
Nowkoelln Flowmarkt scraper.
Static WordPress site — dates are listed as recurring every 2nd Sunday.
We extract the listed dates and generate events from them.
"""

import logging
import re
from datetime import date, datetime
from typing import Any

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SITE_URL = "https://www.nowkoelln.de"
VENUE_NAME = "Nowkoelln Flowmarkt"
VENUE_ADDRESS = "Maybachufer, 12047 Berlin"
VENUE_LAT = 52.4875
VENUE_LNG = 13.4260
VENUE_NEIGHBORHOOD = "Neukölln"

# Market runs 10:00–18:00
START_HOUR = 10
END_HOUR = 18


class NowkoellnScraper(BaseScraper):
    source_name = "nowkoelln"

    def scrape(self) -> list[dict[str, Any]]:
        try:
            resp = self.get(SITE_URL)
            soup = BeautifulSoup(resp.text, "lxml")
        except Exception as e:
            logger.error("Nowkoelln fetch error: %s", e)
            return self._generate_recurring_dates()

        # Extract explicit dates from page
        dates = self._extract_dates_from_page(soup)

        if not dates:
            logger.info("nowkoelln: no dates found on page, generating recurring schedule")
            dates = self._generate_recurring_dates()

        events = []
        for d in dates:
            events.append(
                {
                    "title": "Nowkoelln Flowmarkt",
                    "venue_name": VENUE_NAME,
                    "address": VENUE_ADDRESS,
                    "lat": VENUE_LAT,
                    "lng": VENUE_LNG,
                    "neighborhood": VENUE_NEIGHBORHOOD,
                    "start_time": datetime(d.year, d.month, d.day, START_HOUR, 0).isoformat(),
                    "end_time": datetime(d.year, d.month, d.day, END_HOUR, 0).isoformat(),
                    "description": (
                        "Berlin's beloved Neukölln flea market at Maybachufer canal. "
                        "Second-hand goods, handmade crafts, art, music, and food. "
                        "Every second Sunday, rain or shine."
                    ),
                    "price": "Free",
                    "price_cents": 0,
                    "image_url": None,
                    "source_url": SITE_URL,
                    "source_id": f"nowkoelln-{d.isoformat()}",
                    "category": "market",
                    "subcategory": "flea market",
                    "tags": [
                        "flea market",
                        "secondhand",
                        "handmade",
                        "outdoor",
                        "neukölln",
                        "maybachufer",
                        "free entry",
                    ],
                    "source_tags": [],
                    "source": self.source_name,
                }
            )

        logger.info("nowkoelln: generated %d market dates", len(events))
        return events

    def _extract_dates_from_page(self, soup: BeautifulSoup) -> list[date]:
        """Parse explicit market dates listed on the website."""
        dates = []
        text = soup.get_text(" ", strip=True)

        # Pattern: "22. März 2026" or "22.03.2026"
        DE_MONTHS = {
            "januar": 1,
            "februar": 2,
            "märz": 3,
            "april": 4,
            "mai": 5,
            "juni": 6,
            "juli": 7,
            "august": 8,
            "september": 9,
            "oktober": 10,
            "november": 11,
            "dezember": 12,
        }

        # German long format
        for match in re.finditer(
            r"(\d{1,2})\.\s*(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s*(\d{4})",
            text,
            re.IGNORECASE,
        ):
            try:
                day = int(match.group(1))
                month = DE_MONTHS[match.group(2).lower()]
                year = int(match.group(3))
                d = date(year, month, day)
                if d >= date.today():
                    dates.append(d)
            except (ValueError, KeyError):
                continue

        # Numeric format
        for match in re.finditer(r"(\d{2})\.(\d{2})\.(\d{4})", text):
            try:
                d = date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
                if d >= date.today() and d not in dates:
                    dates.append(d)
            except ValueError:
                continue

        return sorted(set(dates))

    def _generate_recurring_dates(self) -> list[date]:
        """
        Generate every 2nd Sunday for the next 6 months.
        Nowkoelln runs every 2 weeks on Sunday.
        """
        from datetime import timedelta

        dates = []
        today = date.today()

        # Find the next Sunday
        days_until_sunday = (6 - today.weekday()) % 7
        next_sunday = today + timedelta(days=days_until_sunday)

        # Generate biweekly Sundays for 6 months
        current = next_sunday
        end_date = today.replace(
            month=today.month + 6 if today.month <= 6 else today.month - 6,
            year=today.year + (1 if today.month > 6 else 0),
        )

        count = 0
        while current <= end_date and count < 15:
            dates.append(current)
            current += timedelta(weeks=2)
            count += 1

        return dates
