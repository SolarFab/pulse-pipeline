"""
startbahn.berlin scraper — community events at Genezarethkirche, Neukölln.

Uses WordPress REST API to list events (MEC plugin posts),
then fetches each event page for JSON-LD structured data (dates, times, venue).
Many events are recurring (weekly yoga, playgroups, etc.) — the scraper
generates occurrences for the next 4 weeks from the base date.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from html import unescape
from typing import Any

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

WP_API = "https://startbahn.berlin/wp-json/wp/v2/mec-events"
PAGE_SIZE = 50

VENUE_NAME = "Startbahn – Genezarethkirche"
VENUE_ADDRESS = "Herrfurthplatz 14, 12049 Berlin"
VENUE_LAT = 52.4770
VENUE_LNG = 13.4221

_STRIP_HTML = re.compile(r"<[^>]+>")

_MIN_DATE = "2025-01-01"
WEEKS_AHEAD = 4  # generate this many weeks of recurring events

# Day name → weekday index (Monday=0)
_DAY_PATTERNS: dict[str, int] = {
    "monday": 0,
    "montag": 0,
    "montags": 0,
    "mondays": 0,
    "tuesday": 1,
    "dienstag": 1,
    "dienstags": 1,
    "tuesdays": 1,
    "wednesday": 2,
    "mittwoch": 2,
    "mittwochs": 2,
    "wednesdays": 2,
    "thursday": 3,
    "donnerstag": 3,
    "donnerstags": 3,
    "thursdays": 3,
    "friday": 4,
    "freitag": 4,
    "freitags": 4,
    "fridays": 4,
    "saturday": 5,
    "samstag": 5,
    "samstags": 5,
    "saturdays": 5,
    "sunday": 6,
    "sonntag": 6,
    "sonntags": 6,
    "sundays": 6,
}


class StartbahnScraper(BaseScraper):
    source_name = "startbahn"

    def scrape(self) -> list[dict[str, Any]]:
        posts = self._fetch_posts()
        logger.info("startbahn: fetched %d posts", len(posts))

        events: list[dict[str, Any]] = []
        for post in posts:
            parsed = self._parse_post(post)
            events.extend(parsed)

        # Filter old events
        today_str = date.today().isoformat()
        filtered = [e for e in events if str(e.get("start_time", ""))[:10] >= today_str]
        logger.info(
            "startbahn: %d future events (%d past filtered out)",
            len(filtered),
            len(events) - len(filtered),
        )
        return filtered

    def _fetch_posts(self) -> list[dict]:
        """Fetch all MEC event posts via WP REST API."""
        try:
            return self.get_json(
                WP_API,
                params={
                    "per_page": PAGE_SIZE,
                    "_fields": "id,title,link,excerpt,content,date,tpgb_featured_images",
                },
            )
        except Exception as e:
            logger.error("startbahn: failed to fetch posts: %s", e)
            return []

    def _parse_post(self, post: dict) -> list[dict[str, Any]]:
        """Parse a single MEC event post. Fetches event page for JSON-LD dates."""
        title = _strip_html(post.get("title", {}).get("rendered", ""))
        link = post.get("link", "")
        excerpt = _strip_html(post.get("excerpt", {}).get("rendered", ""))
        content_html = post.get("content", {}).get("rendered", "")
        content_text = _strip_html(content_html)

        # Extract image
        images = post.get("tpgb_featured_images", {})
        image_url = None
        if images:
            for size in ("large", "medium_large", "medium", "full"):
                if size in images and images[size]:
                    img = images[size]
                    if isinstance(img, list) and img:
                        image_url = img[0]
                    elif isinstance(img, str):
                        image_url = img
                    break

        # Fetch event page for JSON-LD structured data
        json_ld = self._fetch_json_ld(link)

        if not json_ld:
            # Fallback: extract dates from content
            return self._events_from_content(title, link, excerpt, image_url, content_text)

        start_str = json_ld.get("startDate", "")
        end_str = json_ld.get("endDate", "")
        if not start_str:
            return []

        # Extract price
        price = None
        offers = json_ld.get("offers", {})
        if isinstance(offers, dict):
            p = offers.get("price")
            if p is not None:
                try:
                    price = "Free" if float(p) == 0 else f"€{p}"
                except (ValueError, TypeError):
                    pass

        # Determine category
        category = self._infer_category(title, excerpt, content_text)

        # Build description
        description = excerpt[:500] if excerpt else content_text[:500]

        # Parse base date/time
        try:
            start_dt = datetime.fromisoformat(
                start_str.replace("+00:00", "+00:00").replace("Z", "+00:00")
            )
        except ValueError:
            start_dt = None

        end_dt = None
        if end_str:
            try:
                end_dt = datetime.fromisoformat(
                    end_str.replace("+00:00", "+00:00").replace("Z", "+00:00")
                )
            except ValueError:
                pass

        if not start_dt:
            return []

        # Check for recurrence pattern in content
        recurrence_day = self._detect_recurrence(title, excerpt, content_text)

        # Generate events
        base_event = {
            "title": title,
            "venue_name": VENUE_NAME,
            "address": VENUE_ADDRESS,
            "lat": VENUE_LAT,
            "lng": VENUE_LNG,
            "description": description,
            "price": price,
            "source_url": link,
            "category": category,
            "tags": ["neukölln", "community"],
            "image_url": image_url,
            "source": self.source_name,
        }

        if recurrence_day is not None:
            return self._generate_recurring(base_event, start_dt, end_dt, recurrence_day)
        else:
            # Single event
            event = {
                **base_event,
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat() if end_dt else None,
                "source_id": f"startbahn-{title[:40]}-{start_dt.date().isoformat()}",
            }
            return [event]

    def _fetch_json_ld(self, url: str) -> dict | None:
        """Fetch event page and extract JSON-LD Event data."""
        if not url:
            return None
        try:
            resp = self.get(url)
            html = resp.text
            pattern = re.compile(
                r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                re.DOTALL,
            )
            for match in pattern.finditer(html):
                try:
                    data = json.loads(match.group(1))
                    if isinstance(data, list):
                        for item in data:
                            if item.get("@type") == "Event":
                                return item
                    elif isinstance(data, dict) and data.get("@type") == "Event":
                        return data
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            logger.debug("startbahn: failed to fetch JSON-LD from %s: %s", url, e)
        return None

    def _detect_recurrence(self, title: str, excerpt: str, content: str) -> int | None:
        """Detect weekly recurrence from text. Returns weekday index (0=Mon) or None."""
        combined = (title + " " + excerpt + " " + content).lower()
        for pattern, weekday in _DAY_PATTERNS.items():
            # Look for "every Tuesday", "on Tuesdays", "Dienstags", "Join Sarah on Tuesdays"
            if re.search(rf"\b{re.escape(pattern)}\b", combined):
                return weekday
        return None

    def _generate_recurring(
        self,
        base: dict,
        start_dt: datetime,
        end_dt: datetime | None,
        weekday: int,
    ) -> list[dict[str, Any]]:
        """Generate WEEKS_AHEAD occurrences of a weekly recurring event."""
        today = date.today()
        duration = (end_dt - start_dt) if end_dt else None

        # Find the next occurrence of this weekday from today
        days_ahead = (weekday - today.weekday()) % 7
        if days_ahead == 0 and start_dt.date() < today:
            days_ahead = 7
        next_date = today + timedelta(days=days_ahead)

        events = []
        for i in range(WEEKS_AHEAD):
            d = next_date + timedelta(weeks=i)
            occ_start = datetime(
                d.year,
                d.month,
                d.day,
                start_dt.hour,
                start_dt.minute,
                start_dt.second,
            )
            occ_end = None
            if duration:
                occ_end = occ_start + duration

            events.append(
                {
                    **base,
                    "start_time": occ_start.isoformat(),
                    "end_time": occ_end.isoformat() if occ_end else None,
                    "source_id": f"startbahn-{base['title'][:40]}-{d.isoformat()}",
                }
            )

        return events

    def _events_from_content(
        self,
        title: str,
        link: str,
        excerpt: str,
        image_url: str | None,
        content_text: str,
    ) -> list[dict[str, Any]]:
        """Fallback: extract dates from content text."""
        date_matches = re.findall(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", content_text)
        if not date_matches:
            return []

        category = self._infer_category(title, excerpt, content_text)
        description = excerpt[:500] if excerpt else content_text[:500]
        events = []

        for day, month, year in date_matches:
            start_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            events.append(
                {
                    "title": title,
                    "venue_name": VENUE_NAME,
                    "address": VENUE_ADDRESS,
                    "lat": VENUE_LAT,
                    "lng": VENUE_LNG,
                    "start_time": start_date,
                    "end_time": None,
                    "description": description,
                    "price": None,
                    "source_url": link,
                    "source_id": f"startbahn-{title[:40]}-{start_date}",
                    "category": category,
                    "tags": ["neukölln", "community"],
                    "image_url": image_url,
                    "source": self.source_name,
                }
            )

        return events

    def _infer_category(self, title: str, excerpt: str, content: str) -> str | None:
        """Infer category from event text."""
        combined = (title + " " + excerpt).lower()
        if any(w in combined for w in ("yoga", "meditation", "healing", "spirituality", "mindful")):
            return "outdoors"
        if any(w in combined for w in ("flohmarkt", "flea market", "familienflohmarkt")):
            return "markets"
        if any(
            w in combined for w in ("konzert", "concert", "music", "tanz", "dance", "kunst", "art")
        ):
            return "culture"
        if any(
            w in combined
            for w in ("kinder", "toddler", "family", "familie", "krabbel", "spielgruppe")
        ):
            return "family"
        if any(w in combined for w in ("workshop", "kurs", "class")):
            return "workshops"
        return None  # let categorizer decide


def _strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities."""
    return unescape(_STRIP_HTML.sub("", text)).strip()
