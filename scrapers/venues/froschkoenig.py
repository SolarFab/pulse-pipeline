"""
froschkoenig-berlin.de scraper — Stummfilm & Piano (silent film nights).

Weekly Wednesday event at Froschkönig bar in Neukölln.
Uses WordPress REST API to fetch upcoming event posts.
Falls back to generating next 4 Wednesdays if no posts found.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from html import unescape
from typing import Any

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

WP_API = "https://froschkoenig-berlin.de/wp-json/wp/v2/posts"

VENUE_NAME = "Froschkönig"
VENUE_ADDRESS = "Weisestraße 17, 12049 Berlin"
VENUE_LAT = 52.4768
VENUE_LNG = 13.4239

_STRIP_HTML = re.compile(r"<[^>]+>")

DESCRIPTION = (
    "Laufende Bilder e.V. präsentiert: Stummfilme mit Live-Pianobegleitung. "
    "Jeden Mittwoch ab 20:30 im Froschkönig, Neukölln. Eintritt frei."
)



class FroschkoenigScraper(BaseScraper):
    source_name = "froschkoenig"

    def scrape(self) -> list[dict[str, Any]]:
        events = self._from_wp_api()

        # Only use dates from the website — no generation
        today_str = date.today().isoformat()
        future = [e for e in events if e["start_time"][:10] >= today_str]
        logger.info("froschkoenig: %d future events", len(future))
        return future

    def _from_wp_api(self) -> list[dict[str, Any]]:
        """Fetch event posts from WordPress REST API."""
        events = []
        try:
            posts = self.get_json(
                WP_API,
                params={
                    "per_page": 10,
                    "_fields": "id,title,link,excerpt,date",
                },
            )
        except Exception as e:
            logger.error("froschkoenig: failed to fetch posts: %s", e)
            return []

        for post in posts:
            title = _strip_html(post.get("title", {}).get("rendered", ""))
            link = post.get("link", "")

            # Parse date from title: "Stummfilm & Piano | Mittwoch | 18.03.26 | 20:30"
            date_match = re.search(r"(\d{1,2})\.(\d{2})\.(\d{2,4})", title)
            if not date_match:
                continue

            day, month, year = date_match.groups()
            if len(year) == 2:
                year = f"20{year}"
            date_str = f"{year}-{month}-{day.zfill(2)}"

            # Extract time from title
            time_match = re.search(r"(\d{1,2}:\d{2})\s*$", title.strip())
            time_str = time_match.group(1) if time_match else "20:30"

            # Extract film name from title (between pipes)
            film_name = None
            parts = [p.strip() for p in title.split("|")]
            for part in parts:
                if part.lower().startswith("stummfilm"):
                    continue
                if re.match(r"\d", part):  # date or time
                    continue
                if part.lower() in ("mittwoch", "mittwochs"):
                    continue
                film_name = part
                break

            event_title = "Stummfilm & Piano"
            desc = DESCRIPTION
            if film_name:
                event_title = f"Stummfilm & Piano: {film_name}"
                desc = f"{film_name} — {DESCRIPTION}"

            events.append({
                "title": event_title,
                "venue_name": VENUE_NAME,
                "address": VENUE_ADDRESS,
                "lat": VENUE_LAT,
                "lng": VENUE_LNG,
                "start_time": f"{date_str}T{time_str}:00",
                "end_time": None,
                "description": desc,
                "price": "Free",
                "source_url": link or "https://froschkoenig-berlin.de/",
                "source_id": f"froschkoenig-stummfilm-{date_str}",
                "category": "culture",
                "subcategory": "cinema",
                "tags": ["silent-film", "live-piano", "neukölln", "free"],
                "image_url": None,
                "source": self.source_name,
            })

        return events



def _strip_html(text: str) -> str:
    return unescape(_STRIP_HTML.sub("", text)).strip()
