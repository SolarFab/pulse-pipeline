"""
Klunkerkranich scraper.
Rooftop bar/culture venue in Neukölln — concerts, markets, club nights, art events.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

EVENTS_URL = "https://klunkerkranich.org/events/"
VENUE_NAME = "Klunkerkranich"
VENUE_ADDRESS = "Karl-Marx-Str. 66, 12043 Berlin (Rooftop, 5th floor)"
VENUE_LAT = 52.4836
VENUE_LNG = 13.4302
VENUE_NEIGHBORHOOD = "Neukölln"


class KlunkerkranichScraper(BaseScraper):
    source_name = "klunkerkranich"

    def scrape(self) -> list[dict[str, Any]]:
        try:
            resp = self.get(EVENTS_URL)
            soup = BeautifulSoup(resp.text, "lxml")
        except Exception as e:
            logger.error("Klunkerkranich fetch error: %s", e)
            return []

        events = []

        # JSON-LD
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

        # HTML fallback (WordPress typically)
        if not events:
            events = self._parse_html(soup)

        logger.info("klunkerkranich: found %d events", len(events))
        return events

    def _parse_jsonld(self, item: dict) -> dict | None:
        try:
            title = item.get("name", "").strip()
            if not title:
                return None

            description = (item.get("description") or "").strip()[:400] or None

            offers = item.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price_val = offers.get("price")
            if price_val is not None:
                price = "Free" if float(price_val) == 0 else f"€{price_val}"
            else:
                price = None

            image = item.get("image")
            image_url = (
                image
                if isinstance(image, str)
                else (image[0] if isinstance(image, list) and image else None)
            )

            url = item.get("url") or EVENTS_URL

            return {
                "title": title,
                "venue_name": VENUE_NAME,
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
                "tags": ["rooftop", "neukölln", "outdoor"],
                "source_tags": [],
                "source": self.source_name,
            }
        except Exception as e:
            logger.warning("Klunkerkranich JSON-LD parse error: %s", e)
            return None

    def _parse_html(self, soup: BeautifulSoup) -> list[dict]:
        events = []
        # Klunkerkranich uses wp_events plugin: <article class="o-card type-wp_events ...">
        cards = soup.find_all("article", class_=re.compile(r"type-wp_events", re.I))

        for card in cards:
            try:
                title_el = card.find(["h2", "h3", "h4"])
                title = title_el.get_text(strip=True) if title_el else None
                if not title:
                    continue

                link_el = card.find("a", href=True)
                source_url = link_el["href"] if link_el else EVENTS_URL

                # Extract date from URL: /events/2026-03-12-event-slug/
                date_match = re.search(r"/events/(\d{4}-\d{2}-\d{2})-", source_url)

                # Extract times from card text: "16:00 — 01:00"
                card_text = card.get_text(" ", strip=True)
                time_match = re.search(r"(\d{1,2}:\d{2})\s*[—–-]\s*(\d{1,2}:\d{2})", card_text)

                start_time = None
                end_time = None
                if date_match:
                    date_str = date_match.group(1)
                    start_hour = time_match.group(1) if time_match else "20:00"
                    start_time = f"{date_str}T{start_hour}:00"

                    if time_match:
                        end_hour_str = time_match.group(2)
                        # If end time < start time, it's the next day
                        sh = int(start_hour.split(":")[0])
                        eh = int(end_hour_str.split(":")[0])
                        if eh < sh:
                            from datetime import datetime, timedelta

                            next_day = (
                                datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)
                            ).strftime("%Y-%m-%d")
                            end_time = f"{next_day}T{end_hour_str}:00"
                        else:
                            end_time = f"{date_str}T{end_hour_str}:00"

                img_el = card.find("img")
                image_url = img_el.get("src") if img_el else None

                events.append(
                    {
                        "title": title,
                        "venue_name": VENUE_NAME,
                        "address": VENUE_ADDRESS,
                        "lat": VENUE_LAT,
                        "lng": VENUE_LNG,
                        "neighborhood": VENUE_NEIGHBORHOOD,
                        "start_time": start_time,
                        "end_time": end_time,
                        "description": None,
                        "image_url": image_url,
                        "source_url": source_url,
                        "source_id": source_url.rstrip("/").split("/")[-1],
                        "category": self._infer_category(title, ""),
                        "tags": ["rooftop", "neukölln"],
                        "source_tags": [],
                        "source": self.source_name,
                    }
                )
            except Exception:
                continue

        return events

    def _infer_category(self, title: str, description: str) -> str:
        combined = (title + " " + description).lower()
        if any(w in combined for w in ("konzert", "music", "band", "jazz", "live")):
            return "music"
        if any(w in combined for w in ("party", "dj", "club", "dance", "rave")):
            return "nightlife"
        if any(w in combined for w in ("markt", "market", "flohmarkt")):
            return "market"
        if any(w in combined for w in ("kunst", "art", "ausstellung", "exhibition")):
            return "culture"
        if any(w in combined for w in ("yoga", "sport", "fitness")):
            return "wellness"
        return "social"
