"""
kulturdaten.berlin API scraper.
Base URL: https://api-v2.kulturdaten.berlin/api
No auth required for reading. 13,800+ events.

Event structure:
  - attractions[0].referenceLabel.de  -> title
  - locations[0].referenceLabel.de    -> venue name
  - schedule.startDate/startTime      -> start_time
  - admission.ticketType              -> price
  - identifier                        -> source_id

Separate calls to /api/attractions/{id} and /api/locations/{id} for
description, tags, and address -- results are cached to avoid N+1 calls.
"""

from __future__ import annotations

import logging
import os as _os
import time
from typing import Any

_MAX_PAGES = int(_os.environ.get("KULTURDATEN_MAX_PAGES", "0"))

from scrapers.base import BaseScraper
from pipeline.taxonomy import SOURCE_TAG_CATEGORY_MAP, classify_event

logger = logging.getLogger(__name__)

BASE_URL = "https://api-v2.kulturdaten.berlin/api"

ADMISSION_MAP = {
    "ticketType.freeOfCharge": "Free",
    "ticketType.advance": None,
    "ticketType.donation": "Pay what you want",
}


class KulturdatenScraper(BaseScraper):
    source_name = "kulturdaten"

    def __init__(self):
        super().__init__()
        self._location_cache: dict[str, dict] = {}
        self._attraction_cache: dict[str, dict] = {}

    def scrape(self) -> list[dict[str, Any]]:
        # Phase 1: Fetch all events (fast, no detail calls)
        raw_events: list[dict] = []
        page = 1
        page_size = 100

        while True:
            try:
                data = self.get_json(
                    f"{BASE_URL}/events",
                    params={"page": page, "pageSize": page_size},
                )
            except Exception as e:
                logger.error("kulturdaten API error on page %d: %s", page, e)
                break

            events_raw = data.get("data", {}).get("events", [])
            if not events_raw:
                break

            raw_events.extend(events_raw)

            total = data.get("data", {}).get("totalCount", 0)
            fetched = page * page_size
            if page % 20 == 0:
                logger.info("kulturdaten: page %d -- %d / %d", page, min(fetched, total), total)

            if fetched >= total:
                break
            if _MAX_PAGES and page >= _MAX_PAGES:
                logger.info("kulturdaten: stopping at page %d (KULTURDATEN_MAX_PAGES=%d)", page, _MAX_PAGES)
                break
            page += 1

        logger.info("kulturdaten: fetched %d raw events in %d pages", len(raw_events), page)

        # Phase 2: Batch-fetch unique locations and attractions
        location_ids: set[str] = set()
        attraction_ids: set[str] = set()
        for item in raw_events:
            for loc in item.get("locations", []):
                lid = loc.get("referenceId")
                if lid:
                    location_ids.add(lid)
            for attr in item.get("attractions", []):
                aid = attr.get("referenceId")
                if aid:
                    attraction_ids.add(aid)

        logger.info("kulturdaten: fetching %d unique locations", len(location_ids))
        for i, lid in enumerate(location_ids):
            self._get_location(lid)
            if (i + 1) % 100 == 0:
                logger.info("kulturdaten: locations %d / %d", i + 1, len(location_ids))

        logger.info("kulturdaten: fetching %d unique attractions", len(attraction_ids))
        for i, aid in enumerate(attraction_ids):
            self._get_attraction(aid)
            if (i + 1) % 100 == 0:
                logger.info("kulturdaten: attractions %d / %d", i + 1, len(attraction_ids))

        # Phase 3: Parse all events using cached data
        all_events: list[dict] = []
        for item in raw_events:
            parsed = self._parse_event(item)
            if parsed:
                all_events.append(parsed)

        logger.info("kulturdaten: parsed %d events", len(all_events))
        return all_events

    def _parse_event(self, item: dict) -> dict | None:
        try:
            if item.get("status") != "event.published":
                return None
            if item.get("scheduleStatus") in ("event.cancelled", "event.postponed"):
                return None

            schedule = item.get("schedule", {})
            start_date = schedule.get("startDate")
            start_time_str = schedule.get("startTime", "00:00:00")
            if not start_date:
                return None

            if start_time_str and start_time_str != "00:00:00":
                start_time = f"{start_date}T{start_time_str}"
            else:
                start_time = start_date

            end_date = schedule.get("endDate")
            end_time_str = schedule.get("endTime", "00:00:00")
            end_time = None
            if end_date and end_time_str and end_time_str != "00:00:00":
                end_time = f"{end_date}T{end_time_str}"
            elif end_date and end_date != start_date:
                end_time = end_date

            attractions = item.get("attractions", [])
            if not attractions:
                return None
            attraction_ref = attractions[0]
            title = (
                attraction_ref.get("referenceLabel", {}).get("de")
                or attraction_ref.get("referenceLabel", {}).get("en")
                or ""
            ).strip()
            if not title:
                return None

            locations = item.get("locations", [])
            venue_name = "Berlin"
            location_id = None
            if locations:
                loc_ref = locations[0]
                venue_name = (
                    loc_ref.get("referenceLabel", {}).get("de")
                    or loc_ref.get("referenceLabel", {}).get("en")
                    or "Berlin"
                ).strip()
                location_id = loc_ref.get("referenceId")

            address, neighborhood, venue_website = None, None, None
            if location_id:
                loc_data = self._get_location(location_id)
                if loc_data:
                    addr = loc_data.get("address", {})
                    address = ", ".join(filter(None, [
                        addr.get("streetAddress", ""),
                        addr.get("postalCode", ""),
                        addr.get("addressLocality", ""),
                    ])) or None
                    neighborhood = loc_data.get("borough")
                    # Try to get venue website from location contact
                    contact = loc_data.get("contact", {})
                    if isinstance(contact, dict):
                        venue_website = contact.get("website") or contact.get("url")
                    if venue_website and not venue_website.startswith(("http://", "https://")):
                        venue_website = f"https://{venue_website}"

            attraction_id = attraction_ref.get("referenceId")
            description, tags, category, source_subcategory, source_url, source_tags = None, [], None, None, None, []
            if attraction_id:
                attr_data = self._get_attraction(attraction_id)
                if attr_data:
                    desc_obj = attr_data.get("description", {})
                    description = (
                        desc_obj.get("de") or desc_obj.get("en") or ""
                    ).strip() or None

                    raw_tags = attr_data.get("tags", [])
                    category, source_subcategory = self._map_tags(raw_tags)
                    tags = [t.split(".")[-1].lower() for t in raw_tags]
                    source_tags = raw_tags  # preserve original kulturdaten tags

                    website = attr_data.get("website")
                    ext_links = attr_data.get("externalLinks", [])
                    source_url = website or (ext_links[0].get("url") if ext_links else None)

                    # Ensure URL has scheme
                    if source_url and not source_url.startswith(("http://", "https://")):
                        source_url = f"https://{source_url}"

            # Enrich with keyword-based subcategory + tag extraction
            classification = classify_event(
                title=title,
                description=description,
                category=category,
                existing_tags=tags,
            )
            # Subcategory: prefer source_tag mapping, fall back to keyword match
            subcategory = source_subcategory or classification["subcategory"]
            keyword_tags = classification["keyword_tags"] or []
            # Merge keyword tags into tags list (deduplicated, English tags)
            enriched_tags = list(tags)
            for kt in keyword_tags:
                if kt not in enriched_tags:
                    enriched_tags.append(kt)

            admission = item.get("admission", {})
            ticket_type = admission.get("ticketType", "")
            price = ADMISSION_MAP.get(ticket_type)

            return {
                "title": title,
                "venue_name": venue_name,
                "address": address,
                "neighborhood": neighborhood,
                "start_time": start_time,
                "end_time": end_time,
                "description": description,
                "price": price,
                "source_url": source_url or venue_website or f"https://kulturdaten.berlin/events/{item['identifier']}",
                "source_id": item.get("identifier"),
                "category": category,
                "subcategory": subcategory,
                "tags": enriched_tags,
                "source_tags": source_tags,
                "source": self.source_name,
            }
        except Exception as e:
            logger.warning("kulturdaten parse error: %s", e)
            return None

    def _get_location(self, location_id: str) -> dict | None:
        if location_id in self._location_cache:
            return self._location_cache[location_id]
        try:
            data = self.get_json(f"{BASE_URL}/locations/{location_id}")
            loc = data.get("data", {}).get("location", {})
            self._location_cache[location_id] = loc
            return loc
        except Exception:
            self._location_cache[location_id] = {}
            return None

    def _get_attraction(self, attraction_id: str) -> dict | None:
        if attraction_id in self._attraction_cache:
            return self._attraction_cache[attraction_id]
        try:
            data = self.get_json(f"{BASE_URL}/attractions/{attraction_id}")
            attr = data.get("data", {}).get("attraction", {})
            self._attraction_cache[attraction_id] = attr
            return attr
        except Exception:
            self._attraction_cache[attraction_id] = {}
            return None

    def _map_tags(self, tags: list[str]) -> tuple[str | None, str | None]:
        """Map kulturdaten source tags to (category, subcategory)."""
        for tag in tags:
            mapping = SOURCE_TAG_CATEGORY_MAP.get(tag)
            if mapping:
                cat, sub = mapping
                if cat:  # skip excluded tags (Police etc.)
                    return cat, sub
        return None, None
