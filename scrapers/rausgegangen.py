"""
Rausgegangen Berlin scraper.
Best local aggregator for underground/curated Berlin events.
Uses JSON-LD structured data + HTML fallback.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://rausgegangen.de"
BERLIN_EVENTS_URL = f"{BASE_URL}/berlin/"

# Category pages → our category mapping
CATEGORY_PAGES = {
    f"{BASE_URL}/berlin/kategorie/konzerte-und-musik/": "music",
    f"{BASE_URL}/berlin/kategorie/party/": "nightlife",
    f"{BASE_URL}/berlin/kategorie/markt/": "markets",
    f"{BASE_URL}/berlin/kategorie/theater/": "culture",
    f"{BASE_URL}/berlin/tipps-fuer-heute/": None,  # mixed, let categorizer decide
    f"{BASE_URL}/berlin/tipps-fuers-wochenende/": None,
}

# Category slug → our category
CATEGORY_MAP = {
    "konzerte-musik": "music",
    "konzerte": "music",
    "musik": "music",
    "party": "nightlife",
    "clubs": "nightlife",
    "nachtleben": "nightlife",
    "theater": "culture",
    "shows-performances": "culture",
    "comedy": "nightlife",
    "film": "culture",
    "kino": "culture",
    "maerkte": "markets",
    "markte": "markets",
    "flohmarkt": "markets",
    "kunst-ausstellungen": "culture",
    "ausstellungen": "culture",
    "kultur": "culture",
    "sport-outdoor": "outdoors",
    "yoga": "outdoors",
    "essen-trinken": "food",
    "food": "food",
}


class RausgegangeScraper(BaseScraper):
    source_name = "rausgegangen"

    def scrape(self) -> list[dict[str, Any]]:
        events = []
        seen_urls: set[str] = set()

        # Scrape each category page + today/weekend pages
        for page_url, category_hint in CATEGORY_PAGES.items():
            try:
                resp = self.get(page_url)
                soup = BeautifulSoup(resp.text, "lxml")
            except Exception as e:
                logger.warning("Failed to fetch %s: %s", page_url, e)
                continue

            event_urls = self._extract_event_urls_from_jsonld(soup)
            if not event_urls:
                event_urls = self._extract_event_urls_from_html(soup)

            new_urls = [u for u in event_urls if u not in seen_urls]
            seen_urls.update(new_urls)
            logger.info(
                "rausgegangen: %s → %d new event URLs", page_url.split("/")[-2], len(new_urls)
            )

            for url in new_urls[:50]:
                event = self._scrape_event_page(url)
                if event:
                    if category_hint and not event.get("category"):
                        event["category"] = category_hint
                    events.append(event)

        logger.info("rausgegangen: total %d events", len(events))
        return events

    def _extract_event_urls_from_jsonld(self, soup: BeautifulSoup) -> list[str]:
        urls = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if data.get("@type") == "ItemList":
                    for item in data.get("itemListElement", []):
                        url = item.get("url") or item.get("item", {}).get("url")
                        if url:
                            urls.append(url)
            except (json.JSONDecodeError, AttributeError):
                continue
        return urls

    def _extract_event_urls_from_html(self, soup: BeautifulSoup) -> list[str]:
        urls = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # Rausgegangen event URLs pattern: /berlin/veranstaltungen/some-slug/
            if re.match(r"^/berlin/veranstaltungen/[^/]+/$", href):
                full_url = f"{BASE_URL}{href}"
                if full_url not in urls:
                    urls.append(full_url)
        return urls

    def _scrape_event_page(self, url: str) -> dict | None:
        try:
            resp = self.get(url)
            soup = BeautifulSoup(resp.text, "lxml")
        except Exception as e:
            logger.warning("Failed to fetch event page %s: %s", url, e)
            return None

        # Try JSON-LD first
        event = self._parse_jsonld_event(soup, url)
        if event:
            return event

        # Fallback: parse HTML
        return self._parse_html_event(soup, url)

    def _parse_jsonld_event(self, soup: BeautifulSoup, source_url: str) -> dict | None:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if data.get("@type") != "Event":
                    continue

                name = data.get("name", "").strip()
                if not name:
                    continue

                location = data.get("location") or {}
                venue_name = location.get("name", "").strip() or "Unknown"
                address_obj = location.get("address") or {}
                address = (
                    address_obj.get("streetAddress", "") or address_obj
                    if isinstance(address_obj, str)
                    else ""
                )
                geo = location.get("geo") or {}
                lat = geo.get("latitude")
                lng = geo.get("longitude")

                description = (data.get("description") or "").strip() or None

                offers = data.get("offers") or []
                price = None
                if offers:
                    if isinstance(offers, list):
                        offer = offers[0]
                    else:
                        offer = offers
                    p = offer.get("price")
                    currency = offer.get("priceCurrency", "€")
                    if p is not None:
                        price = "Free" if float(p) == 0 else f"{currency}{p}"

                image = data.get("image")
                image_url = (
                    image
                    if isinstance(image, str)
                    else (image[0] if isinstance(image, list) and image else None)
                )

                # Category from URL slug
                slug = source_url.rstrip("/").split("/")[-1]
                category = self._category_from_slug(slug)

                # Extract category slug from source URL for source_tags
                slug = source_url.rstrip("/").split("/")[-1]

                return {
                    "title": name,
                    "venue_name": venue_name,
                    "address": address or None,
                    "lat": float(lat) if lat else None,
                    "lng": float(lng) if lng else None,
                    "start_time": data.get("startDate"),
                    "end_time": data.get("endDate"),
                    "description": description,
                    "price": price,
                    "image_url": image_url,
                    "source_url": source_url,
                    "source_id": source_url.rstrip("/").split("/")[-1],
                    "category": category,
                    "source_tags": [slug] if slug else [],
                    "source": self.source_name,
                }
            except Exception as e:
                logger.debug("JSON-LD parse error at %s: %s", source_url, e)
                continue
        return None

    def _parse_html_event(self, soup: BeautifulSoup, source_url: str) -> dict | None:
        """Fallback HTML parser when JSON-LD is absent."""
        try:
            title_el = soup.find("h1") or soup.find("h2")
            title = title_el.get_text(strip=True) if title_el else None
            if not title:
                return None

            # Venue — look for common patterns
            venue_el = soup.find(class_=re.compile(r"venue|location|ort", re.I))
            venue_name = venue_el.get_text(strip=True) if venue_el else "Unknown"

            # Date — look for time tags
            time_el = soup.find("time")
            start_time = time_el.get("datetime") if time_el else None

            # Description
            desc_el = soup.find(class_=re.compile(r"description|beschreibung|text|content", re.I))
            description = desc_el.get_text(strip=True)[:500] if desc_el else None

            slug = source_url.rstrip("/").split("/")[-1]

            return {
                "title": title,
                "venue_name": venue_name,
                "start_time": start_time,
                "description": description,
                "source_url": source_url,
                "source_id": slug,
                "category": self._category_from_slug(slug),
                "source_tags": [slug] if slug else [],
                "source": self.source_name,
            }
        except Exception as e:
            logger.warning("HTML parse fallback failed at %s: %s", source_url, e)
            return None

    def _category_from_slug(self, slug: str) -> str | None:
        slug_lower = slug.lower()
        for key, cat in CATEGORY_MAP.items():
            if key in slug_lower:
                return cat
        return None
