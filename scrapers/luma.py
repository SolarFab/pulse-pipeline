"""
Luma (lu.ma) scraper.
Fetches public events in Berlin via Luma's discover API.
Falls back to scraping the lu.ma/berlin page for __NEXT_DATA__ if the API fails.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Luma discover API endpoints
DISCOVER_PAGINATED_URL = "https://api.lu.ma/discover/get-paginated-events"
DISCOVER_PLACE_URL = "https://api.lu.ma/discover/get-events"

# Berlin coordinates
BERLIN_LAT = 52.52
BERLIN_LNG = 13.405
GEO_RADIUS = "25km"

# Fallback: scrape the lu.ma city page
BERLIN_PAGE_URL = "https://lu.ma/berlin"

# Categories we can infer from Luma tags/descriptions
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "music": ["music", "concert", "dj", "live music", "band", "jazz", "electronic"],
    "nightlife": [
        "party",
        "club night",
        "rave",
        "afterparty",
        "after-party",
        "comedy",
        "standup",
        "stand-up",
        "karaoke",
    ],
    "culture": [
        "art",
        "gallery",
        "exhibition",
        "museum",
        "film",
        "cinema",
        "theater",
        "theatre",
        "reading",
    ],
    "meetups": ["meetup", "networking", "social", "community", "game", "quiz", "trivia"],
    "outdoors": ["yoga", "meditation", "wellness", "breathwork", "fitness", "run", "workout"],
    "food": [
        "food",
        "cooking",
        "tasting",
        "supper club",
        "pop-up kitchen",
        "brunch",
        "dinner",
        "happy hour",
        "drinks",
    ],
    "markets": ["flea market", "flohmarkt", "craft market", "market"],
    "workshops": ["workshop", "class", "course", "tutorial", "hack"],
}

# Luma hides exact venues until registration for many events; geo info then only
# carries the city. A city is NOT a venue ("@ Berlin" is meaningless in a Berlin app).
_CITYISH = {"berlin", "potsdam", "deutschland", "germany"}


def pick_venue_name(geo_info: dict, address: str | None, location_name: str | None) -> str:
    """Venue name that is never just a city: place fields first, then the address's
    first segment (which on Luma is usually the actual venue), else 'TBA'."""
    city = str(geo_info.get("city") or "").strip()

    def usable(v: str | None) -> str | None:
        v = (v or "").strip()
        if not v or v.lower() in _CITYISH or (city and v.lower() == city.lower()):
            return None
        return v

    for candidate in (geo_info.get("place_name"), geo_info.get("name"), location_name):
        if usable(candidate):
            return usable(candidate)  # type: ignore[return-value]
    if address:
        first = address.split(",")[0]
        if usable(first):
            return usable(first)  # type: ignore[return-value]
    return "TBA"


class LumaScraper(BaseScraper):
    source_name = "luma"

    def scrape(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        # Strategy 1: paginated geo-based discover API
        events = self._scrape_paginated_api()
        if events:
            logger.info("luma: got %d events from paginated API", len(events))
            unique = self._deduplicate(events)
            self._enrich_descriptions(unique)
            return unique

        # Strategy 2: place-based discover API
        events = self._scrape_place_api()
        if events:
            logger.info("luma: got %d events from place API", len(events))
            unique = self._deduplicate(events)
            self._enrich_descriptions(unique)
            return unique

        # Strategy 3: scrape the Berlin page HTML for __NEXT_DATA__
        events = self._scrape_berlin_page()
        if events:
            logger.info("luma: got %d events from Berlin page fallback", len(events))
            unique = self._deduplicate(events)
            self._enrich_descriptions(unique)
            return unique

        logger.warning("luma: all strategies failed, returning 0 events")
        return []

    # ── Description enrichment ───────────────────────────────────────────────

    def _enrich_descriptions(self, events: list[dict[str, Any]]) -> None:
        """Fetch og:description from event pages for events missing descriptions."""
        import time

        need_desc = [e for e in events if not e.get("description") and e.get("source_url")]
        if not need_desc:
            return

        logger.info("luma: enriching descriptions for %d events", len(need_desc))
        enriched = 0
        for event in need_desc:
            try:
                resp = self.get(event["source_url"])
                match = re.search(
                    r'<meta\s+(?:property="og:description"|name="description")\s+content="([^"]+)"',
                    resp.text,
                )
                if match:
                    import html

                    desc = html.unescape(match.group(1)).strip()
                    if desc and len(desc) > 10:
                        event["description"] = desc[:500]
                        enriched += 1
            except Exception as e:
                logger.debug(
                    "luma: description fetch failed for %s: %s", event.get("source_url"), e
                )

            if enriched % 20 == 0 and enriched > 0:
                logger.info("luma: enriched %d / %d descriptions", enriched, len(need_desc))
            time.sleep(0.5)

        logger.info("luma: enriched %d / %d events with descriptions", enriched, len(need_desc))

    # ── Strategy 1: Paginated geo API ─────────────────────────────────────────

    def _scrape_paginated_api(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        pagination_cursor: str | None = None
        max_pages = 5

        for page in range(max_pages):
            params: dict[str, Any] = {
                "pagination_limit": 50,
                "geo_latitude": str(BERLIN_LAT),
                "geo_longitude": str(BERLIN_LNG),
                "geo_radius": GEO_RADIUS,
            }
            if pagination_cursor:
                params["pagination_cursor"] = pagination_cursor

            try:
                data = self.get_json(
                    DISCOVER_PAGINATED_URL,
                    params=params,
                    headers={"Accept": "application/json"},
                )
            except Exception as e:
                logger.warning("luma paginated API failed (page %d): %s", page, e)
                break

            entries = data.get("entries") or data.get("events") or data.get("data") or []
            if not entries:
                # Try unwrapping if the structure differs
                if isinstance(data, list):
                    entries = data
                else:
                    break

            for entry in entries:
                parsed = self._parse_entry(entry)
                if parsed:
                    events.append(parsed)

            # Handle pagination
            pagination_cursor = data.get("next_cursor") or data.get("pagination_cursor")
            has_more = data.get("has_more", False)
            if not pagination_cursor or not has_more:
                break

        return events

    # ── Strategy 2: Place-based API ───────────────────────────────────────────

    def _scrape_place_api(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        try:
            data = self.get_json(
                DISCOVER_PLACE_URL,
                params={"discover_place_api_id": "plc-berlin"},
                headers={"Accept": "application/json"},
            )
        except Exception as e:
            logger.warning("luma place API failed: %s", e)
            return []

        entries = data.get("entries") or data.get("events") or data.get("data") or []
        if isinstance(data, list):
            entries = data

        for entry in entries:
            parsed = self._parse_entry(entry)
            if parsed:
                events.append(parsed)

        return events

    # ── Strategy 3: HTML fallback ─────────────────────────────────────────────

    def _scrape_berlin_page(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        try:
            resp = self.get(BERLIN_PAGE_URL)
            html = resp.text
        except Exception as e:
            logger.warning("luma Berlin page fetch failed: %s", e)
            return []

        # Extract __NEXT_DATA__ JSON from the page
        match = re.search(
            r'<script\s+id="__NEXT_DATA__"\s+type="application/json">\s*({.*?})\s*</script>',
            html,
            re.DOTALL,
        )
        if not match:
            logger.warning("luma: could not find __NEXT_DATA__ in Berlin page")
            return []

        try:
            next_data = json.loads(match.group(1))
        except json.JSONDecodeError as e:
            logger.warning("luma: failed to parse __NEXT_DATA__: %s", e)
            return []

        # Navigate the Next.js data structure to find events
        page_props = next_data.get("props", {}).get("pageProps", {})

        # Try common paths where Luma stores event data
        raw_events = (
            page_props.get("initialData", {}).get("data", {}).get("events")
            or page_props.get("events")
            or page_props.get("initialData", {}).get("events")
            or []
        )

        # Sometimes events are nested inside featured sections
        if not raw_events:
            sections = page_props.get("initialData", {}).get("data", {}).get("sections", [])
            for section in sections:
                section_events = section.get("events") or section.get("entries") or []
                raw_events.extend(section_events)

        for entry in raw_events:
            parsed = self._parse_entry(entry)
            if parsed:
                events.append(parsed)

        return events

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parse_entry(self, entry: dict) -> dict[str, Any] | None:
        """Parse a single Luma event entry into our raw event schema."""
        try:
            # Luma wraps event data in different ways depending on the endpoint
            event = entry.get("event") or entry.get("data") or entry
            calendar = entry.get("calendar") or {}

            title = (event.get("name") or event.get("title") or "").strip()
            if not title:
                return None

            # Event ID and slug
            event_id = event.get("api_id") or event.get("id") or event.get("event_id")
            slug = event.get("url") or event.get("slug") or event_id
            if slug and slug.startswith("http"):
                source_url = slug
            elif slug:
                source_url = f"https://lu.ma/{slug}"
            else:
                source_url = None

            # Times
            start_time = event.get("start_at") or event.get("start_time") or event.get("startTime")
            end_time = event.get("end_at") or event.get("end_time") or event.get("endTime")

            # Skip past events
            if start_time:
                try:
                    from dateutil import parser as dateparser

                    start_dt = dateparser.parse(start_time)
                    if start_dt and start_dt.replace(tzinfo=UTC) < datetime.now(UTC) - timedelta(
                        hours=6
                    ):
                        return None
                except Exception:
                    pass

            # Location info
            geo_info = event.get("geo_address_info") or event.get("location") or {}
            if isinstance(geo_info, str):
                # Sometimes location is just a string (may still be a bare city)
                address = geo_info
                venue_name = pick_venue_name({}, geo_info, None)
                lat = None
                lng = None
            else:
                geo_json = event.get("geo_address_json")
                geo_json_address = (
                    geo_json.get("full_address") if isinstance(geo_json, dict) else None
                )
                address = (
                    geo_info.get("full_address")
                    or geo_info.get("address")
                    or geo_info.get("formatted_address")
                    or geo_json_address
                )
                venue_name = pick_venue_name(geo_info, address, event.get("location_name"))
                lat = geo_info.get("latitude") or geo_info.get("lat")
                lng = geo_info.get("longitude") or geo_info.get("lng") or geo_info.get("lon")

            # Also check top-level geo fields
            if not lat:
                lat = event.get("geo_latitude") or event.get("latitude")
            if not lng:
                lng = event.get("geo_longitude") or event.get("longitude")

            # Cast lat/lng to float if present
            if lat is not None:
                try:
                    lat = float(lat)
                except (ValueError, TypeError):
                    lat = None
            if lng is not None:
                try:
                    lng = float(lng)
                except (ValueError, TypeError):
                    lng = None

            # Fallback venue name
            if not venue_name:
                venue_name = address or "TBA"

            # Description
            description = (
                event.get("description")
                or event.get("description_short")
                or event.get("summary")
                or ""
            ).strip() or None

            # Truncate overly long descriptions
            if description and len(description) > 1000:
                description = description[:997] + "..."

            # Cover image
            image_url = (
                event.get("cover_url")
                or event.get("image_url")
                or event.get("cover_image_url")
                or calendar.get("cover_url")
            )

            # Tags from Luma
            raw_tags = event.get("tags") or event.get("labels") or []
            if isinstance(raw_tags, str):
                raw_tags = [raw_tags]

            # Preserve original Luma tags
            source_tags = [t for t in raw_tags if isinstance(t, str)]

            # Infer category from tags and description
            category = self._infer_category(title, description, raw_tags)

            # Build normalized tags list
            tags = [t.lower().strip() for t in raw_tags if isinstance(t, str)][:10]

            return {
                "title": title,
                "venue_name": venue_name,
                "address": address,
                "start_time": start_time,
                "end_time": end_time,
                "description": description,
                "image_url": image_url,
                "source_url": source_url,
                "source_id": str(event_id) if event_id else None,
                "category": category,
                "tags": tags if tags else None,
                "source_tags": source_tags,
                "lat": lat,
                "lng": lng,
                "source": self.source_name,
            }
        except Exception as e:
            logger.debug("luma event parse error: %s", e)
            return None

    def _infer_category(
        self,
        title: str,
        description: str | None,
        tags: list[str],
    ) -> str:
        """Guess the best category from title, description, and tags."""
        text = " ".join(
            [
                title.lower(),
                (description or "").lower(),
                " ".join(t.lower() for t in tags if isinstance(t, str)),
            ]
        )

        # Score each category by keyword matches
        best_category = "meetups"  # default for Luma events
        best_score = 0

        for category, keywords in CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > best_score:
                best_score = score
                best_category = category

        return best_category

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _deduplicate(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove duplicate events by source_id."""
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for e in events:
            sid = e.get("source_id")
            if sid and sid in seen:
                continue
            if sid:
                seen.add(sid)
            unique.append(e)
        logger.info("luma: %d unique events after dedup", len(unique))
        return unique
