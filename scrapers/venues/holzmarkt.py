"""
Holzmarkt 25 scraper.
Creative community space on the Spree — Bar25, Kater Blau, Pampa, restaurants, culture.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

EVENTS_URL = "https://www.holzmarkt.com/programm/"
VENUE_NAME = "Holzmarkt 25"
VENUE_ADDRESS = "Holzmarktstraße 25, 10243 Berlin"
VENUE_LAT = 52.5131
VENUE_LNG = 13.4226
VENUE_NEIGHBORHOOD = "Friedrichshain"


class HolzmarktScraper(BaseScraper):
    source_name = "holzmarkt"

    def scrape(self) -> list[dict[str, Any]]:
        try:
            resp = self.get(EVENTS_URL)
            soup = BeautifulSoup(resp.text, "lxml")
        except Exception as e:
            logger.error("Holzmarkt fetch error: %s", e)
            return []

        events = []

        # Try JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") == "Event":
                        event = self._parse_jsonld(item)
                        if event:
                            events.append(event)
            except Exception:
                continue

        # HTML fallback
        if not events:
            events = self._parse_html(soup)

        logger.info("holzmarkt: found %d events", len(events))
        return events

    def _parse_jsonld(self, item: dict) -> dict | None:
        try:
            title = item.get("name", "").strip()
            if not title:
                return None

            description = (item.get("description") or "").strip()[:400] or None
            url = item.get("url") or EVENTS_URL

            offers = item.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price_val = offers.get("price")
            price = (
                "Free"
                if price_val is not None and float(price_val) == 0
                else (f"€{price_val}" if price_val else None)
            )

            image = item.get("image")
            image_url = (
                image
                if isinstance(image, str)
                else (image[0] if isinstance(image, list) and image else None)
            )

            # Sub-venue (Kater Blau, Pampa, etc.)
            performer = item.get("performer") or item.get("location") or {}
            sub_venue = performer.get("name", "") if isinstance(performer, dict) else ""

            return {
                "title": title,
                "venue_name": f"{VENUE_NAME} — {sub_venue}".rstrip(" — ")
                if sub_venue
                else VENUE_NAME,
                "address": VENUE_ADDRESS,
                "lat": VENUE_LAT,
                "lng": VENUE_LNG,
                "neighborhood": VENUE_NEIGHBORHOOD,
                "start_time": item.get("startDate"),
                "end_time": item.get("endDate"),
                "description": description,
                "price": price,
                "image_url": image_url,
                "source_url": url,
                "source_id": url.rstrip("/").split("/")[-1],
                "category": self._infer_category(title, description or ""),
                "tags": ["spree", "friedrichshain", "holzmarkt"],
                "source_tags": [],
                "source": self.source_name,
            }
        except Exception as e:
            logger.warning("Holzmarkt JSON-LD error: %s", e)
            return None

    def _parse_html(self, soup: BeautifulSoup) -> list[dict]:
        events = []
        cards = soup.find_all(
            "article", class_=re.compile(r"event|programm", re.I)
        ) or soup.find_all("div", class_=re.compile(r"event-card|program-item", re.I))

        for card in cards:
            try:
                title_el = card.find(["h2", "h3", "h4"])
                title = title_el.get_text(strip=True) if title_el else None
                if not title:
                    continue

                time_el = card.find("time")
                start_time = time_el.get("datetime") if time_el else None

                link_el = card.find("a", href=True)
                href = link_el["href"] if link_el else None
                source_url = (
                    href
                    if href and href.startswith("http")
                    else (f"https://www.holzmarkt.com{href}" if href else EVENTS_URL)
                )

                desc_el = card.find("p")
                description = desc_el.get_text(strip=True)[:400] if desc_el else None

                events.append(
                    {
                        "title": title,
                        "venue_name": VENUE_NAME,
                        "address": VENUE_ADDRESS,
                        "lat": VENUE_LAT,
                        "lng": VENUE_LNG,
                        "neighborhood": VENUE_NEIGHBORHOOD,
                        "start_time": start_time,
                        "description": description,
                        "source_url": source_url,
                        "source_id": source_url.rstrip("/").split("/")[-1] if source_url else None,
                        "category": self._infer_category(title, description or ""),
                        "tags": ["spree", "friedrichshain"],
                        "source_tags": [],
                        "source": self.source_name,
                    }
                )
            except Exception:
                continue

        return events

    def _infer_category(self, title: str, description: str) -> str:
        combined = (title + " " + description).lower()
        if any(w in combined for w in ("techno", "club", "party", "rave", "dj set", "kater blau")):
            return "nightlife"
        if any(w in combined for w in ("konzert", "live music", "band", "jazz")):
            return "music"
        if any(w in combined for w in ("markt", "market")):
            return "market"
        if any(w in combined for w in ("kunst", "ausstellung", "art", "gallery")):
            return "culture"
        if any(w in combined for w in ("food", "dinner", "restaurant", "bar")):
            return "food"
        return "social"
