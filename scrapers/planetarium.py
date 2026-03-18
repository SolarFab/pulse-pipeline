"""
Stiftung Planetarium Berlin scraper.
API: https://www.planetarium.berlin/api/v1/events?page={n}

Covers:
  - Zeiss-Großplanetarium (Prenzlauer Allee 80)
  - Archenhold-Sternwarte (Alt-Treptow 1)
  - Wilhelm-Foerster-Sternwarte (Munsterdamm 90)

Each "event" (show) has multiple event_times (dates). We expand each
date into a separate event for the map.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

API_URL = "https://www.planetarium.berlin/api/v1/events"

CATEGORY_MAP = {
    "Planetarium": "culture",
    "Kino": "culture",
    "Wissenschaftstheater": "culture",
    "Highlights & Konzerte": "music",
    "Musik": "music",
    "Kinder & Familie": "family",
    "Kita & Schule": "family",
    "Vorträge": "culture",
    "Sternwarte": "culture",
    "Workshops & Kurse": "workshops",
    "Hörspiele & Lesungen": "culture",
}


def strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class PlanetariumScraper(BaseScraper):
    source_name = "planetarium"

    def scrape(self) -> list[dict[str, Any]]:
        all_shows: list[dict] = []
        page = 1

        while True:
            try:
                data = self.get_json(API_URL, params={"page": page})
            except Exception as e:
                logger.error("Planetarium API error on page %d: %s", page, e)
                break

            objects = data.get("objects", [])
            meta = data.get("meta", {})

            if not objects:
                break

            all_shows.extend(objects)
            logger.info("Page %d: %d shows (total: %d)", page, len(objects), len(all_shows))

            if page >= meta.get("total_pages", 1):
                break
            page += 1

        logger.info("Fetched %d shows from planetarium API", len(all_shows))

        # Expand each show into individual events per date
        events: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        for show in all_shows:
            event_times = show.get("event_times") or []
            if not event_times:
                continue

            for et in event_times:
                parsed = self._parse_showtime(show, et, now)
                if parsed:
                    events.append(parsed)

        logger.info("Expanded to %d individual events", len(events))
        return events

    def _parse_showtime(
        self, show: dict, event_time: dict, now: datetime
    ) -> dict[str, Any] | None:
        try:
            title = (show.get("title_de") or show.get("title_en") or "").strip()
            if not title:
                return None

            # Date and time
            date_str = event_time.get("event_date")  # "YYYY-MM-DD"
            start_str = event_time.get("start")  # "HH:MM"
            end_str = event_time.get("end")  # "HH:MM"

            if not date_str or not start_str:
                return None

            start_time = f"{date_str}T{start_str}:00+01:00"
            end_time = f"{date_str}T{end_str}:00+01:00" if end_str else None

            # Skip past events
            try:
                start_dt = datetime.fromisoformat(start_time)
                if start_dt < now:
                    return None
            except Exception:
                pass

            # Venue
            venue_name = show.get("location_name") or "Zeiss-Großplanetarium"
            address = ", ".join(
                str(x) for x in [
                    show.get("street_address"),
                    show.get("postal_code"),
                    show.get("city", "Berlin"),
                ] if x
            )

            # Coordinates (some venues return empty strings)
            lat = show.get("latitude") or None
            lng = show.get("longitude") or None
            if lat:
                try:
                    lat = float(lat)
                except (ValueError, TypeError):
                    lat = None
            if lng:
                try:
                    lng = float(lng)
                except (ValueError, TypeError):
                    lng = None

            # Fallback coordinates for known venues
            if not lat or not lng:
                venue_coords = {
                    "Wilhelm-Foerster-Sternwarte": (52.4575, 13.3411),
                    "Planetarium am Insulaner": (52.4575, 13.3411),
                    "Helleum II": (52.5405, 13.5085),
                }
                if venue_name in venue_coords:
                    lat, lng = venue_coords[venue_name]

            # Description
            desc_html = show.get("press_text_de") or show.get("press_text_en") or ""
            description = strip_html(desc_html)[:800] or None

            # Subtitle
            subtitle = (show.get("subtitle_de") or "").strip()
            if subtitle and description:
                description = f"{subtitle}\n\n{description}"
            elif subtitle:
                description = subtitle

            # Category from API categories
            category = "culture"
            tags = []
            for cat in show.get("categories") or []:
                cat_name = cat.get("title_de", "")
                tags.append(cat_name.lower())
                if cat_name in CATEGORY_MAP:
                    category = CATEGORY_MAP[cat_name]

            # Price
            price = None
            if show.get("free_admission"):
                price = "Free"
            elif show.get("admission_price"):
                price = f"{show['admission_price']}EUR"
                if show.get("reduced_price"):
                    price += f" / {show['reduced_price']}EUR reduced"

            # Image
            image_url = None
            media = show.get("media_files") or []
            if media:
                image_url = media[0].get("url")

            # Source URL
            source_url = show.get("website_de") or show.get("website_en")

            # Unique source ID per show+date
            show_id = show.get("id", "")
            source_id = f"planetarium-{show_id}-{date_str}"

            return {
                "title": title,
                "venue_name": venue_name,
                "address": address,
                "start_time": start_time,
                "end_time": end_time,
                "description": description,
                "image_url": image_url,
                "source_url": source_url,
                "source_id": source_id,
                "category": category,
                "tags": tags if tags else None,
                "lat": lat,
                "lng": lng,
                "price": price,
                "source": self.source_name,
            }
        except Exception as e:
            logger.debug("Planetarium parse error: %s", e)
            return None
