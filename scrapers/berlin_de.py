"""
Berlin.de official city events calendar scraper.
Uses month-based URLs: /events/jahresuebersicht/maerz/, /events/jahresuebersicht/april/ etc.
Category URLs (/events/konzerte/) return 410 Gone.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.berlin.de"

# German month names for URL paths (lowercase, no umlauts)
MONTHS_URL = [
    "januar",
    "februar",
    "maerz",
    "april",
    "mai",
    "juni",
    "juli",
    "august",
    "september",
    "oktober",
    "november",
    "dezember",
]


class BerlinDeScraper(BaseScraper):
    source_name = "berlin_de"

    def scrape(self) -> list[dict[str, Any]]:
        events = []

        # Scrape current month + next month
        urls = self._get_month_urls()
        for url in urls:
            page_events = self._scrape_month_page(url)
            events.extend(page_events)

        logger.info("berlin_de: fetched %d events", len(events))
        return events

    def _get_month_urls(self) -> list[str]:
        """Build URLs for current month and next month."""
        today = date.today()
        current_month_idx = today.month - 1  # 0-based
        next_month_idx = today.month % 12  # wraps Dec→Jan

        return [
            f"{BASE_URL}/events/jahresuebersicht/{MONTHS_URL[current_month_idx]}/",
            f"{BASE_URL}/events/jahresuebersicht/{MONTHS_URL[next_month_idx]}/",
        ]

    def _scrape_month_page(self, url: str) -> list[dict]:
        """Scrape a single month page, following pagination."""
        events = []
        page = 1

        while True:
            page_url = f"{url}?page={page}" if page > 1 else url
            try:
                resp = self.get(page_url)
                soup = BeautifulSoup(resp.text, "lxml")
            except Exception as e:
                logger.error("berlin.de fetch error %s: %s", page_url, e)
                break

            items = self._parse_event_list(soup)
            if not items:
                break

            events.extend(items)

            # Check for next page
            next_link = soup.find("a", class_=re.compile(r"next|weiter", re.I))
            if not next_link:
                # Also check for pagination links
                pager = soup.find(class_=re.compile(r"pager|pagination", re.I))
                if pager:
                    current = pager.find(class_=re.compile(r"active|current", re.I))
                    if current:
                        next_sib = current.find_next_sibling("a") or current.find_next("a")
                        if not next_sib:
                            break
                    else:
                        break
                else:
                    break

            page += 1
            if page > 10:  # safety cap
                break

        return events

    def _parse_event_list(self, soup: BeautifulSoup) -> list[dict]:
        events = []

        # Berlin.de uses various card structures
        cards = (
            soup.find_all("article", class_=re.compile(r"event|veranstaltung|teaser", re.I))
            or soup.find_all("li", class_=re.compile(r"event|veranstaltung|teaser", re.I))
            or soup.find_all("div", class_=re.compile(r"event-item|veranstaltungs|teaser", re.I))
        )

        # If no class-matched cards, try all articles
        if not cards:
            cards = soup.find_all("article")

        for card in cards:
            event = self._parse_card(card)
            if event:
                # Fetch detail page for end_time if we have a source_url
                if event.get("source_url") and not event.get("end_time"):
                    end_time = self._fetch_end_time(event["source_url"])
                    if end_time:
                        event["end_time"] = end_time
                events.append(event)

        return events

    def _parse_card(self, card) -> dict | None:
        try:
            # Title + link
            title_el = card.find(["h2", "h3", "h4"])
            if not title_el:
                # Try finding a link with substantial text
                title_el = card.find("a", href=True)
            if not title_el:
                return None
            title = title_el.get_text(strip=True)
            if not title or len(title) < 3:
                return None

            link_el = card.find("a", href=True)
            source_url = None
            if link_el:
                href = link_el["href"]
                source_url = href if href.startswith("http") else f"{BASE_URL}{href}"

            # Date — <time> tag or text patterns
            start_time = self._extract_date(card)
            if not start_time:
                return None

            # Venue
            venue_el = card.find(class_=re.compile(r"venue|location|ort|place", re.I))
            venue_name = venue_el.get_text(strip=True) if venue_el else "Berlin"

            # Description
            desc_el = card.find(class_=re.compile(r"description|text|teaser|intro|summary", re.I))
            if not desc_el:
                desc_el = card.find("p")
            description = desc_el.get_text(strip=True)[:400] if desc_el else None

            # Image
            img_el = card.find("img")
            image_url = None
            if img_el:
                image_url = img_el.get("src") or img_el.get("data-src")
                if image_url and not image_url.startswith("http"):
                    image_url = f"{BASE_URL}{image_url}"

            # Source ID from URL
            source_id = source_url.rstrip("/").split("/")[-1] if source_url else None

            return {
                "title": title,
                "venue_name": venue_name,
                "start_time": start_time,
                "description": description,
                "image_url": image_url,
                "source_url": source_url,
                "source_id": source_id,
                "category": None,  # let Claude categorizer handle it
                "source_tags": [],
                "source": self.source_name,
            }
        except Exception as e:
            logger.warning("berlin.de card parse error: %s", e)
            return None

    def _fetch_end_time(self, url: str) -> str | None:
        """Fetch the detail page and extract endDate from JSON-LD."""
        try:
            resp = self.get(url)
            for match in re.finditer(
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                resp.text,
                re.DOTALL,
            ):
                data = json.loads(match.group(1))
                items = [data] if isinstance(data, dict) else data
                if isinstance(data, dict) and "@graph" in data:
                    items = data["@graph"]
                for item in items:
                    if item.get("@type") in ("Event", "ScreeningEvent", "MusicEvent"):
                        end_date = item.get("endDate")
                        if end_date:
                            return end_date
        except Exception as e:
            logger.debug("berlin.de detail fetch failed for %s: %s", url, e)
        return None

    def _extract_date(self, card) -> str | None:
        """Try multiple strategies to extract a date from a card."""
        # Strategy 1: <time> tag with datetime attribute
        time_el = card.find("time")
        if time_el:
            dt = time_el.get("datetime")
            if dt:
                return dt
            # Fallback: text content of <time>
            text = time_el.get_text(strip=True)
            if text:
                return text

        # Strategy 2: German date patterns in card text
        text = card.get_text(" ", strip=True)

        # "Fr 27.03.2026 20:00 Uhr" or "27.03.2026"
        match = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})(?:\s+(\d{1,2}:\d{2}))?", text)
        if match:
            date_str = match.group(1)
            time_str = match.group(2)
            if time_str:
                return f"{date_str} {time_str}"
            return date_str

        # "13. März 2026" or "13. und 14. März 2026" — take the first date
        german_months = {
            "januar": "01",
            "februar": "02",
            "märz": "03",
            "maerz": "03",
            "april": "04",
            "mai": "05",
            "juni": "06",
            "juli": "07",
            "august": "08",
            "september": "09",
            "oktober": "10",
            "november": "11",
            "dezember": "12",
        }
        pattern = r"(\d{1,2})\.\s*(" + "|".join(german_months.keys()) + r")(?:\s+(\d{4}))?"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            day = int(match.group(1))
            month = german_months[match.group(2).lower()]
            year = match.group(3) or str(date.today().year)
            return f"{day:02d}.{month}.{year}"

        return None
