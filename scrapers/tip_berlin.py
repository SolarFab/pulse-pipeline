"""
Tip Berlin scraper — Event calendar at tip-berlin.de/event/.
Scrapes category listing pages to collect event URLs, then fetches each
individual event page for JSON-LD structured data (schema.org Event type).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.tip-berlin.de"

# Category pages on the tip-berlin event calendar → our categories
CATEGORY_PAGES = {
    "/event/musik+konzert/": "music",
    "/event/musik+clubnacht/": "nightlife",
    "/event/buehne+schauspiel/": "culture",
    "/event/buehne+kabarett/": "nightlife",
    "/event/buehne+musical/": "culture",
    "/event/ausstellung+andere_orte/": "culture",
    "/event/ausstellung+museen/": "culture",
    "/event/lesungen+vortraege+fuehrungen/": "culture",
    "/event/markt+flohmarkt/": "markets",
    "/event/sonstiges/": "meetups",
}


class TipBerlinScraper(BaseScraper):
    source_name = "tip_berlin"

    def scrape(self) -> list[dict[str, Any]]:
        # Collect unique event URLs from all category pages
        seen_urls: set[str] = set()
        event_urls: list[tuple[str, str]] = []  # (url, category_hint)

        for path, category in CATEGORY_PAGES.items():
            try:
                resp = self.get(f"{BASE_URL}{path}")
                soup = BeautifulSoup(resp.text, "lxml")
            except Exception as e:
                logger.error("tip_berlin: failed to fetch %s: %s", path, e)
                continue

            for a in soup.find_all("a", href=True):
                href = a["href"]
                # Match individual event URLs: /event/category/1465.1234567890/
                if re.search(r"/event/.+/\d+\.\d+/", href):
                    full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
                    if full_url not in seen_urls:
                        seen_urls.add(full_url)
                        event_urls.append((full_url, category))

        logger.info("tip_berlin: found %d unique event URLs", len(event_urls))

        # Fetch each event page and extract JSON-LD
        events = []
        for url, category_hint in event_urls:
            event = self._fetch_event(url, category_hint)
            if event:
                events.append(event)

        logger.info("tip_berlin: extracted %d events", len(events))
        return events

    def _fetch_event(self, url: str, category_hint: str) -> dict | None:
        try:
            resp = self.get(url)
            soup = BeautifulSoup(resp.text, "lxml")
        except Exception as e:
            logger.warning("tip_berlin: failed to fetch %s: %s", url, e)
            return None

        # Look for JSON-LD Event schema
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                items = [data] if isinstance(data, dict) else data
                # Handle @graph wrapper
                if isinstance(data, dict) and "@graph" in data:
                    items = data["@graph"]
                for item in items:
                    if item.get("@type") == "Event":
                        return self._parse_jsonld(item, url, category_hint)
            except Exception:
                continue

        return None

    def _parse_jsonld(self, item: dict, source_url: str, category_hint: str) -> dict | None:
        title = (item.get("name") or "").strip()
        if not title:
            return None

        start_time = item.get("startDate")
        end_time = item.get("endDate")

        location = item.get("location") or {}
        venue_name = location.get("name", "Berlin")
        address_obj = location.get("address") or {}
        address = None
        if isinstance(address_obj, dict):
            street = address_obj.get("streetAddress", "")
            postal = address_obj.get("postalCode", "")
            city = address_obj.get("addressLocality", "Berlin")
            address = f"{street}, {postal} {city}".strip(", ")
        elif isinstance(address_obj, str):
            address = address_obj

        description = (item.get("description") or "").strip()[:400] or None

        image = item.get("image")
        image_url = None
        if isinstance(image, list) and image:
            image_url = image[0]
        elif isinstance(image, str):
            image_url = image

        # Extract source_id from URL: /event/category/1465.1234567890/
        source_id_match = re.search(r"(\d+\.\d+)", source_url)
        source_id = source_id_match.group(1) if source_id_match else source_url

        # Extract category slug from source URL for source_tags
        url_parts = source_url.split("/event/")
        source_tag = url_parts[1].split("/")[0] if len(url_parts) > 1 else None

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
            "category": category_hint,
            "source_tags": [source_tag] if source_tag else [],
            "source": self.source_name,
        }
