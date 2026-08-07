"""
Eventbrite API scraper — uses the Destination Search API (POST).
Free API key at: https://www.eventbrite.com/platform/api-keys
"""

from __future__ import annotations

import html as ihtml
import json
import logging
import os
import re
import time
from typing import Any

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.eventbriteapi.com/v3"
BERLIN_PLACE_ID = "101748799"  # Who's On First ID for Berlin


class EventbriteScraper(BaseScraper):
    _TAGS_RE = re.compile(r"<[^>]+>")
    _LDJSON_RE = re.compile(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", re.DOTALL)

    def _full_description(self, url: str) -> str | None:
        """Fetch the event page's full description (structuredContent, JSON-LD fallback).

        The listing API only returns a ~140-char teaser; the full text is rich
        signal for the categorizer, neighborhood detection and embeddings.
        """
        try:
            time.sleep(0.3)  # polite: one extra page fetch per new event
            resp = self.get(url)
        except Exception:
            return None
        text = resp.text

        def clean(html_text: str) -> str:
            out = ihtml.unescape(self._TAGS_RE.sub(" ", html_text))
            return re.sub(r"\s+", " ", out).strip()

        idx = text.find('"structuredContent":')
        if idx != -1:
            start = text.find("{", idx)
            try:
                blob, _ = json.JSONDecoder().raw_decode(text[start:])
                parts = [
                    m.get("text", "")
                    for m in blob.get("modules", [])
                    if isinstance(m, dict) and m.get("type") == "text"
                ]
                desc = clean(" ".join(parts))
                if desc:
                    return desc[:1500]
            except (json.JSONDecodeError, AttributeError):
                pass
        for block in self._LDJSON_RE.findall(text):
            try:
                data = json.loads(block)
            except json.JSONDecodeError:
                continue
            for item in data if isinstance(data, list) else [data]:
                if isinstance(item, dict) and str(item.get("@type", "")).endswith("Event"):
                    desc = clean(item.get("description") or "")
                    if desc:
                        return desc[:1500]
        return None

    source_name = "eventbrite"

    def scrape(self) -> list[dict[str, Any]]:
        api_key = os.environ.get("EVENTBRITE_API_KEY")
        if not api_key:
            logger.warning("No EVENTBRITE_API_KEY — skipping Eventbrite scraper")
            return []

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }
        events: list[dict[str, Any]] = []
        continuation: str | None = None
        page = 0
        max_pages = 20  # safety limit (~200 events)

        while page < max_pages:
            payload: dict[str, Any] = {
                "event_search": {
                    "places": [BERLIN_PLACE_ID],
                    "dates": ["current_future"],
                },
                "expand.destination_event": [
                    "primary_venue",
                    "image",
                    "ticket_availability",
                ],
            }
            if continuation:
                payload["event_search"]["continuation"] = continuation

            try:
                resp = self.post(
                    f"{BASE_URL}/destination/search/",
                    json=payload,
                    headers=headers,
                )
                data = resp.json()
            except Exception as e:
                logger.error("Eventbrite API error on page %d: %s", page, e)
                break

            results = data.get("events", {}).get("results", [])
            for item in results:
                event = self._parse_event(item)
                if event:
                    events.append(event)

            pagination = data.get("events", {}).get("pagination", {})
            continuation = pagination.get("continuation")
            if not continuation or not results:
                break
            page += 1

        logger.info("eventbrite: fetched %d events across %d pages", len(events), page + 1)
        return events

    def _parse_event(self, item: dict) -> dict[str, Any] | None:
        try:
            title = (item.get("name") or "").strip()
            if not title:
                return None

            # Skip online-only events
            if item.get("is_online_event"):
                return None

            # Skip cancelled events
            if item.get("is_cancelled"):
                return None

            venue = item.get("primary_venue") or {}
            address_obj = venue.get("address") or {}
            venue_name = (
                venue.get("name") or address_obj.get("localized_address_display") or "Unknown"
            )
            address = address_obj.get("localized_address_display")
            lat = address_obj.get("latitude")
            lng = address_obj.get("longitude")

            description = (item.get("summary") or "").strip() or None
            # The listing only carries a ~140-char teaser; the full description
            # (rich signal for categorizer + embeddings) lives on the event page.
            if (not description or len(description) < 300) and item.get("url"):
                full = self._full_description(item["url"])
                if full and len(full) > len(description or ""):
                    description = full

            # Build ISO timestamps from date + time
            start_time = self._build_timestamp(
                item.get("start_date"), item.get("start_time"), item.get("timezone")
            )
            end_time = self._build_timestamp(
                item.get("end_date"), item.get("end_time"), item.get("timezone")
            )

            # Price
            ticket = item.get("ticket_availability") or {}
            price = self._extract_price(ticket)

            # Image
            image = item.get("image") or {}
            image_url = image.get("url")

            # Tags for category hints
            tags = [
                t.get("display_name") for t in (item.get("tags") or []) if t.get("display_name")
            ]
            source_tags = tags.copy()  # preserve original Eventbrite tags

            return {
                "title": title,
                "venue_name": venue_name,
                "address": address,
                "lat": float(lat) if lat else None,
                "lng": float(lng) if lng else None,
                "start_time": start_time,
                "end_time": end_time,
                "description": description,
                "price": price,
                "image_url": image_url,
                "source_url": item.get("url"),
                "source_id": str(item.get("id") or item.get("eventbrite_event_id", "")),
                "tags": tags[:5],
                "source_tags": source_tags,
                "source": self.source_name,
            }
        except Exception as e:
            logger.warning("Eventbrite parse error: %s", e)
            return None

    def _build_timestamp(
        self, date_str: str | None, time_str: str | None, tz: str | None
    ) -> str | None:
        if not date_str:
            return None
        if time_str:
            return f"{date_str}T{time_str}"
        return f"{date_str}T00:00:00"

    def _extract_price(self, ticket: dict) -> str | None:
        if ticket.get("is_free"):
            return "Free"
        if ticket.get("is_sold_out"):
            return "Sold out"
        min_price = ticket.get("minimum_ticket_price", {})
        max_price = ticket.get("maximum_ticket_price", {})
        min_display = min_price.get("display", "")
        max_display = max_price.get("display", "")
        # If min is 0, it's "from free"
        if min_price.get("value") == 0 and max_price.get("value", 0) > 0:
            return f"Free – {max_display}"
        if min_display and max_display and min_display != max_display:
            return f"{min_display} – {max_display}"
        if min_display:
            return min_display
        return None
