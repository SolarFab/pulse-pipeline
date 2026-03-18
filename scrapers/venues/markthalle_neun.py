"""
Markthalle Neun scraper.
Fetches /events listing, follows each event link to get dates from individual pages.
Covers Street Food Thursday, Schnippeldisko, markets, community events.
Also generates recurring events (jam sessions, Street Food Thursday) that
the website only lists a few weeks out.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, date, timedelta
from typing import Any

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

EVENTS_URL = "https://markthalleneun.de/events"
VENUE_NAME = "Markthalle Neun"
VENUE_ADDRESS = "Eisenbahnstraße 42-43, 10997 Berlin"
VENUE_LAT = 52.5022
VENUE_LNG = 13.4315
VENUE_NEIGHBORHOOD = "Kreuzberg"

GERMAN_MONTHS = {
    "januar": 1, "februar": 2, "märz": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}

# Pattern: "10. April" or "3. März 2026"
DATE_PATTERN = re.compile(
    r"(\d{1,2})\.\s*("
    + "|".join(GERMAN_MONTHS.keys())
    + r")(?:\s+(\d{4}))?",
    re.IGNORECASE,
)

# Pattern: "18:00" or "18:00–20:00" or "18:00 - 20:00" or "18:00 Uhr"
TIME_PATTERN = re.compile(r"(\d{1,2}:\d{2})(?:\s*(?:–|-)\s*(\d{1,2}:\d{2}))?")


class MarkthalleScraper(BaseScraper):
    source_name = "markthalle_neun"

    def scrape(self) -> list[dict[str, Any]]:
        # Step 1: Get listing page and extract event links
        events = []
        try:
            resp = self.get(EVENTS_URL)
            soup = BeautifulSoup(resp.text, "html.parser")

            event_links = self._extract_event_links(soup)
            logger.info("markthalle_neun: found %d event links", len(event_links))

            # Step 2: Fetch each individual event page for dates
            for url, title in event_links:
                page_events = self._scrape_event_page(url, title)
                events.extend(page_events)
        except Exception as e:
            logger.error("Markthalle Neun listing fetch error: %s", e)

        # Step 3: Add recurring events that the website only lists partially
        recurring = self._generate_recurring_events()
        # Deduplicate: skip recurring dates already scraped from the website
        scraped_keys = {(e["title"], e["start_time"][:10]) for e in events}
        for r in recurring:
            if (r["title"], r["start_time"][:10]) not in scraped_keys:
                events.append(r)

        logger.info("markthalle_neun: found %d events total (incl. recurring)", len(events))
        return events

    def _extract_event_links(self, soup: BeautifulSoup) -> list[tuple[str, str]]:
        """Extract (url, title) pairs from the listing page."""
        links = []
        seen = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                href = f"https://markthalleneun.de{href}"

            # Only follow /events/slug links (not /events itself)
            if "/events/" not in href or href.rstrip("/") == EVENTS_URL.rstrip("/"):
                continue
            if href in seen:
                continue
            seen.add(href)

            # Get title from heading or link text
            title_el = a.find(["h2", "h3", "h4"])
            title = title_el.get_text(strip=True) if title_el else a.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            links.append((href, title))

        return links

    def _scrape_event_page(self, url: str, fallback_title: str) -> list[dict]:
        """Fetch an individual event page and extract date(s) + details."""
        try:
            resp = self.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            logger.warning("Markthalle event page fetch error %s: %s", url, e)
            return []

        # Try JSON-LD first (some pages have it)
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") == "Event" and item.get("startDate"):
                        event = self._parse_jsonld(item, url)
                        if event:
                            return [event]
            except Exception:
                continue

        # HTML fallback: parse German dates from page text
        # Get title from page
        title_el = soup.find("h1") or soup.find("h2")
        title = title_el.get_text(strip=True) if title_el else fallback_title

        # Get description
        desc = None
        for el in soup.find_all(["p", "div"], class_=re.compile(r"text|desc|content|intro", re.I)):
            text = el.get_text(strip=True)
            if len(text) > 40:
                desc = text[:400]
                break
        if not desc:
            paragraphs = soup.find_all("p")
            for p in paragraphs:
                text = p.get_text(strip=True)
                if len(text) > 40:
                    desc = text[:400]
                    break

        # Get image
        img_el = soup.find("img", src=True)
        image_url = None
        if img_el:
            src = img_el.get("src", "")
            if src and not src.startswith("data:"):
                image_url = src if src.startswith("http") else f"https://markthalleneun.de{src}"

        # Parse dates from full page text
        page_text = soup.get_text(" ", strip=True)
        dates = self._parse_german_dates(page_text)

        if not dates:
            logger.warning("No dates found for %s", url)
            return []

        # Parse time
        start_hour, start_min = None, None
        end_hour, end_min = None, None
        time_match = TIME_PATTERN.search(page_text)
        if time_match:
            parts = time_match.group(1).split(":")
            start_hour, start_min = int(parts[0]), int(parts[1])
            if time_match.group(2):
                parts2 = time_match.group(2).split(":")
                end_hour, end_min = int(parts2[0]), int(parts2[1])

        events = []
        today = date.today()
        for d in dates:
            if d < today:
                continue

            if start_hour is not None:
                start_dt = datetime(d.year, d.month, d.day, start_hour, start_min)
            else:
                start_dt = datetime(d.year, d.month, d.day, 10, 0)  # default 10:00

            end_dt = None
            if end_hour is not None:
                end_dt = datetime(d.year, d.month, d.day, end_hour, end_min)

            events.append({
                "title": title,
                "venue_name": VENUE_NAME,
                "address": VENUE_ADDRESS,
                "lat": VENUE_LAT,
                "lng": VENUE_LNG,
                "neighborhood": VENUE_NEIGHBORHOOD,
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat() if end_dt else None,
                "description": desc,
                "image_url": image_url,
                "source_url": url,
                "source_id": f"{url.rstrip('/').split('/')[-1]}-{d.isoformat()}",
                "category": self._infer_category(title, desc or ""),
                "source_tags": [],
                "source": self.source_name,
            })

        return events

    def _parse_german_dates(self, text: str) -> list[date]:
        """Parse German date patterns like '10. April' or '3. März 2026' from text."""
        today = date.today()
        dates = []

        for match in DATE_PATTERN.finditer(text):
            day = int(match.group(1))
            month_name = match.group(2).lower()
            year_str = match.group(3)

            month = GERMAN_MONTHS.get(month_name)
            if not month:
                continue

            year = int(year_str) if year_str else today.year
            # If the date already passed this year and no year was specified, try next year
            try:
                d = date(year, month, day)
            except ValueError:
                continue

            if not year_str and d < today:
                d = date(year + 1, month, day)

            dates.append(d)

        return sorted(set(dates))

    def _parse_jsonld(self, item: dict, page_url: str) -> dict | None:
        try:
            title = item.get("name", "").strip()
            if not title:
                return None

            description = (item.get("description") or "").strip()[:400] or None

            offers = item.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price_val = offers.get("price")
            currency = offers.get("priceCurrency", "€")
            if price_val is not None:
                price = "Free" if float(price_val) == 0 else f"{currency}{price_val}"
            else:
                price = None

            image = item.get("image")
            image_url = image if isinstance(image, str) else (
                image[0] if isinstance(image, list) and image else None
            )

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
                "source_url": page_url,
                "source_id": page_url.rstrip("/").split("/")[-1],
                "category": self._infer_category(title, description or ""),
                "source_tags": [],
                "source": self.source_name,
            }
        except Exception as e:
            logger.warning("Markthalle JSON-LD parse error: %s", e)
            return None

    def _generate_recurring_events(self) -> list[dict]:
        """Generate recurring weekly events at Markthalle Neun / Bar Neun."""
        today = date.today()
        events = []

        RECURRING = [
            {
                "title": "New Standard Jam Session",
                "weekday": 1,  # Tuesday
                "start_hour": 20, "start_min": 0,
                "end_hour": 0, "end_min": 0,  # midnight (next day)
                "venue_name": "Bar Neun (Markthalle Neun)",
                "description": (
                    "Every Tuesday @ Bar Neun (Markthalle Neun, Kreuzberg) 20:00–00:00. "
                    "Jazz, Blues, Funk and more! Hosted by Lionel Haas (piano), "
                    "Daryl Taylor (bass), and Shinichi Nakajima (drums) — "
                    "joined by some of the city's top musicians. "
                    "Free entrance. Donations welcome."
                ),
                "category": "music",
                "subcategory": "jazz",
                "tags": ["jazz", "jam session", "live-music", "blues", "funk", "free entry", "kreuzberg"],
                "price": "Free",
                "price_cents": 0,
            },
            {
                "title": "Street Food Thursday",
                "weekday": 3,  # Thursday
                "start_hour": 17, "start_min": 0,
                "end_hour": 22, "end_min": 0,
                "venue_name": VENUE_NAME,
                "description": (
                    "Berlin's original street food market. Every Thursday, "
                    "Markthalle Neun fills up with food stalls from around the world. "
                    "A Kreuzberg institution since 2013."
                ),
                "category": "food",
                "subcategory": "street food",
                "tags": ["street food", "food market", "international", "kreuzberg", "weekly"],
                "price": "Eintritt frei",
                "price_cents": 0,
            },
        ]

        for r in RECURRING:
            dates = self._upcoming_weekdays(today, r["weekday"], weeks=8)
            for d in dates:
                start_dt = datetime(d.year, d.month, d.day, r["start_hour"], r["start_min"])
                if r["end_hour"] < r["start_hour"]:
                    next_day = d + timedelta(days=1)
                    end_dt = datetime(next_day.year, next_day.month, next_day.day, r["end_hour"], r["end_min"])
                else:
                    end_dt = datetime(d.year, d.month, d.day, r["end_hour"], r["end_min"])

                events.append({
                    "title": r["title"],
                    "venue_name": r["venue_name"],
                    "address": VENUE_ADDRESS,
                    "lat": VENUE_LAT,
                    "lng": VENUE_LNG,
                    "neighborhood": VENUE_NEIGHBORHOOD,
                    "start_time": start_dt.isoformat(),
                    "end_time": end_dt.isoformat(),
                    "description": r["description"],
                    "price": r["price"],
                    "price_cents": r["price_cents"],
                    "source_url": EVENTS_URL,
                    "source_id": f"markthalle-{r['title'].lower().replace(' ', '-')}-{d.isoformat()}",
                    "category": r["category"],
                    "subcategory": r["subcategory"],
                    "tags": r["tags"],
                    "source_tags": [],
                    "source": self.source_name,
                })

        return events

    @staticmethod
    def _upcoming_weekdays(today: date, weekday: int, weeks: int = 8) -> list[date]:
        """Return the next `weeks` occurrences of `weekday` (0=Mon, 6=Sun)."""
        days_ahead = (weekday - today.weekday()) % 7
        if days_ahead == 0:
            next_date = today
        else:
            next_date = today + timedelta(days=days_ahead)
        return [next_date + timedelta(weeks=i) for i in range(weeks)]

    def _infer_category(self, title: str, description: str) -> str:
        combined = (title + " " + description).lower()
        if any(w in combined for w in ("flohmarkt", "markt", "market", "vintage", "secondhand")):
            return "market"
        if any(w in combined for w in ("food", "essen", "street food", "kochen", "cooking", "dinner")):
            return "food"
        if any(w in combined for w in ("konzert", "musik", "music", "jazz", "band")):
            return "music"
        if any(w in combined for w in ("party", "disko", "disco", "dance", "tanzen")):
            return "nightlife"
        if any(w in combined for w in ("kinder", "family", "familie")):
            return "social"
        return "social"
