"""
Berlin Wochenmärkte (weekly markets) scraper.
Generates recurring events for the next 8 weeks based on fixed schedules.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

TZ = "+01:00"

# (name, address, neighborhood, lat, lng, day_of_week, start_hour, start_min, end_hour, end_min)
# day_of_week: 0=Monday … 6=Sunday
MARKETS: list[tuple[str, str, str, float, float, int, int, int, int, int]] = [
    # Herrfurthplatz – Saturday
    ("Wochenmarkt Herrfurthplatz", "Herrfurthplatz, Neukölln", "Neukölln",
     52.4778, 13.4226, 5, 8, 0, 14, 0),
    # Boxhagener Platz – Saturday
    ("Wochenmarkt Boxhagener Platz", "Boxhagener Platz, Friedrichshain", "Friedrichshain",
     52.5113, 13.4584, 5, 9, 0, 15, 30),
    # Kollwitzplatz – Thursday
    ("Wochenmarkt Kollwitzplatz", "Kollwitzplatz, Prenzlauer Berg", "Prenzlauer Berg",
     52.5341, 13.4178, 3, 12, 0, 19, 0),
    # Kollwitzplatz – Saturday
    ("Wochenmarkt Kollwitzplatz", "Kollwitzplatz, Prenzlauer Berg", "Prenzlauer Berg",
     52.5341, 13.4178, 5, 9, 0, 16, 0),
    # Winterfeldtplatz – Wednesday
    ("Wochenmarkt Winterfeldtplatz", "Winterfeldtplatz, Schöneberg", "Schöneberg",
     52.4953, 13.3547, 2, 8, 0, 14, 0),
    # Winterfeldtplatz – Saturday
    ("Wochenmarkt Winterfeldtplatz", "Winterfeldtplatz, Schöneberg", "Schöneberg",
     52.4953, 13.3547, 5, 8, 0, 16, 0),
    # Karl-August-Platz – Wednesday
    ("Wochenmarkt Karl-August-Platz", "Karl-August-Platz, Charlottenburg", "Charlottenburg",
     52.5076, 13.3118, 2, 8, 0, 14, 0),
    # Karl-August-Platz – Saturday
    ("Wochenmarkt Karl-August-Platz", "Karl-August-Platz, Charlottenburg", "Charlottenburg",
     52.5076, 13.3118, 5, 8, 0, 14, 0),
    # Türkenmarkt am Maybachufer – Tuesday
    ("Türkenmarkt am Maybachufer", "Maybachufer, Neukölln", "Neukölln",
     52.4952, 13.4229, 1, 11, 0, 18, 0),
    # Türkenmarkt am Maybachufer – Friday
    ("Türkenmarkt am Maybachufer", "Maybachufer, Neukölln", "Neukölln",
     52.4952, 13.4229, 4, 11, 0, 18, 0),
    # Arkonaplatz – Sunday
    ("Wochenmarkt Arkonaplatz", "Arkonaplatz, Mitte", "Mitte",
     52.5346, 13.3996, 6, 10, 0, 16, 0),
    # Südstern – Thursday
    ("Wochenmarkt Südstern", "Südstern, Kreuzberg", "Kreuzberg",
     52.4880, 13.3945, 3, 8, 0, 13, 0),
    # Südstern – Saturday
    ("Wochenmarkt Südstern", "Südstern, Kreuzberg", "Kreuzberg",
     52.4880, 13.3945, 5, 8, 0, 13, 0),
    # Rathaus Schöneberg – Wednesday
    ("Wochenmarkt am Rathaus Schöneberg", "John-F.-Kennedy-Platz, Schöneberg", "Schöneberg",
     52.4838, 13.3430, 2, 8, 0, 14, 0),
    # Rathaus Schöneberg – Saturday
    ("Wochenmarkt am Rathaus Schöneberg", "John-F.-Kennedy-Platz, Schöneberg", "Schöneberg",
     52.4838, 13.3430, 5, 8, 0, 14, 0),
    # Ökomarkt Chamissoplatz – Saturday
    ("Ökomarkt Chamissoplatz", "Chamissoplatz, Kreuzberg", "Kreuzberg",
     52.4886, 13.3897, 5, 9, 0, 15, 0),
    # Kranoldplatz – Thursday
    ("Wochenmarkt Kranoldplatz", "Kranoldplatz, Lichterfelde", "Lichterfelde",
     52.4338, 13.3150, 3, 8, 0, 13, 0),
    # Leopoldplatz – Tuesday
    ("Wochenmarkt Leopoldplatz", "Leopoldplatz, Wedding", "Wedding",
     52.5506, 13.3553, 1, 8, 0, 13, 0),
    # Leopoldplatz – Saturday
    ("Wochenmarkt Leopoldplatz", "Leopoldplatz, Wedding", "Wedding",
     52.5506, 13.3553, 5, 8, 0, 13, 0),
]

DESCRIPTION = (
    "Wöchentlicher Markt mit frischem Obst, Gemüse, Blumen und regionalen Produkten."
)

TAGS = ["wochenmarkt", "markt", "regional", "bio"]


def _slug(name: str) -> str:
    """Create a URL-safe slug from a market name."""
    return (
        name.lower()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
        .replace(" ", "-")
        .replace(".", "")
    )


class WochenmaerkteScraper(BaseScraper):
    source_name = "wochenmaerkte"

    def scrape(self) -> list[dict[str, Any]]:
        today = date.today()
        events: list[dict[str, Any]] = []

        for (
            name, address, neighborhood, lat, lng,
            weekday, sh, sm, eh, em,
        ) in MARKETS:
            dates = self._upcoming_dates(today, weekday, weeks=8)
            slug = _slug(name)

            for d in dates:
                start = datetime(d.year, d.month, d.day, sh, sm)
                end = datetime(d.year, d.month, d.day, eh, em)

                events.append({
                    "title": name,
                    "venue_name": name,
                    "address": address,
                    "lat": lat,
                    "lng": lng,
                    "neighborhood": neighborhood,
                    "start_time": f"{start.isoformat()}{TZ}",
                    "end_time": f"{end.isoformat()}{TZ}",
                    "description": DESCRIPTION,
                    "price": "Eintritt frei",
                    "source_url": "",
                    "source_id": f"wochenmarkt-{slug}-{d.isoformat()}",
                    "category": "market",
                    "subcategory": "wochenmarkt",
                    "tags": TAGS,
                    "source_tags": [],
                    "source": self.source_name,
                })

        logger.info("wochenmaerkte: generated %d events", len(events))
        return events

    @staticmethod
    def _upcoming_dates(today: date, weekday: int, weeks: int = 8) -> list[date]:
        """Return the next *weeks* occurrences of *weekday* starting from today."""
        days_ahead = (weekday - today.weekday()) % 7
        if days_ahead == 0:
            next_date = today
        else:
            next_date = today + timedelta(days=days_ahead)

        return [next_date + timedelta(weeks=i) for i in range(weeks)]
