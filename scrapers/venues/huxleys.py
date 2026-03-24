"""
Huxley's Neue Welt scraper.
Fetches the /events listing page (all events on one static HTML page),
then optionally follows detail pages for genre/description/image.
Covers 130+ upcoming concerts and live events.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

EVENTS_URL = "https://huxleysneuewelt.de/events"
BASE_URL = "https://huxleysneuewelt.de"
VENUE_NAME = "Huxleys Neue Welt"
VENUE_ADDRESS = "Hasenheide 107-113, 10967 Berlin"
VENUE_LAT = 52.4864
VENUE_LNG = 13.4215
VENUE_NEIGHBORHOOD = "Neukölln"

GERMAN_MONTHS = {
    "januar": 1, "februar": 2, "märz": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "dezember": 12,
    "jan": 1, "feb": 2, "mär": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dez": 12,
}


class HuxleysScraper(BaseScraper):
    source_name = "huxleys"

    def scrape(self) -> list[dict[str, Any]]:
        resp = self.get(EVENTS_URL)
        if not resp:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        events: list[dict[str, Any]] = []

        # Find all event links — each event is an <a> wrapping the event card
        links = soup.select("a[href*='/event/']")
        seen_urls: set[str] = set()

        for link in links:
            href = link.get("href", "")
            if not href or href in seen_urls:
                continue
            seen_urls.add(href)

            url = href if href.startswith("http") else BASE_URL + href
            event = self._parse_listing_entry(link, url)
            if event:
                events.append(event)

        logger.info("Found %d events on listing page", len(events))

        # Enrich with detail pages (genre, description, image)
        enriched = 0
        for event in events:
            try:
                detail = self._scrape_detail(event["source_url"])
                if detail:
                    if detail.get("description"):
                        event["description"] = detail["description"]
                    if detail.get("image_url"):
                        event["image_url"] = detail["image_url"]
                    if detail.get("tags"):
                        event["source_tags"] = detail["tags"]
                    enriched += 1
            except Exception as e:
                logger.debug("Detail page failed for %s: %s", event.get("title"), e)

        logger.info("Enriched %d/%d events with detail pages", enriched, len(events))
        return events

    def _parse_listing_entry(self, link_tag: Any, url: str) -> dict[str, Any] | None:
        """Parse a single event entry from the listing page."""
        text = link_tag.get_text(" ", strip=True)
        if not text:
            return None

        # Extract date from URL slug: /event/2026-03-24-artist-name
        date_match = re.search(r"/event/(\d{4}-\d{2}-\d{2})", url)
        if not date_match:
            # Try extracting from the text (e.g. "24März")
            date_obj = self._parse_date_from_text(text)
            if not date_obj:
                return None
        else:
            date_str = date_match.group(1)
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                return None

        # Extract times: "Beginn: 20:00" and "Einlass: 19:00"
        show_match = re.search(r"Beginn:\s*(\d{1,2}:\d{2})", text)
        doors_match = re.search(r"Einlass:\s*(\d{1,2}:\d{2})", text)

        show_time = show_match.group(1) if show_match else "20:00"
        doors_time = doors_match.group(1) if doors_match else None

        # Build start time
        h, m = map(int, show_time.split(":"))
        start_dt = date_obj.replace(hour=h, minute=m)
        start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%S+01:00")

        # End time: assume ~3 hours after start for concerts
        end_dt = start_dt.replace(hour=min(h + 3, 23), minute=m)
        end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%S+01:00")

        # Extract artist name — remove date/time parts from text
        artist = text
        # Remove patterns like "24März", "Beginn: 20:00", "Einlass: 19:00", "Ausverkauft"
        artist = re.sub(r"\d{1,2}\s*(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\w*", "", artist, flags=re.IGNORECASE)
        artist = re.sub(r"(?:Beginn|Einlass):\s*\d{1,2}:\d{2}", "", artist)
        artist = re.sub(r"Ausverkauft", "", artist, flags=re.IGNORECASE)
        artist = re.sub(r"\s*\|\s*", " ", artist)
        artist = re.sub(r"\s+", " ", artist).strip()

        if not artist or len(artist) < 2:
            return None

        # Check sold out
        is_sold_out = "ausverkauft" in text.lower()
        price = "Sold out" if is_sold_out else None

        return {
            "title": artist,
            "venue_name": VENUE_NAME,
            "address": VENUE_ADDRESS,
            "lat": VENUE_LAT,
            "lng": VENUE_LNG,
            "neighborhood": VENUE_NEIGHBORHOOD,
            "start_time": start_iso,
            "end_time": end_iso,
            "description": f"Doors: {doors_time}" if doors_time else None,
            "category": "music",
            "source_url": url,
            "source_id": url.split("/event/")[-1] if "/event/" in url else None,
            "source": self.source_name,
            "price": price,
            "image_url": None,
            "source_tags": [],
        }

    def _parse_date_from_text(self, text: str) -> datetime | None:
        """Parse date from listing text like '24März'."""
        match = re.search(
            r"(\d{1,2})\s*(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)",
            text,
            re.IGNORECASE,
        )
        if not match:
            return None

        day = int(match.group(1))
        month_name = match.group(2).lower()
        month = GERMAN_MONTHS.get(month_name)
        if not month:
            return None

        now = datetime.now()
        year = now.year
        try:
            dt = datetime(year, month, day)
        except ValueError:
            return None

        # If date is in the past, assume next year
        if dt.date() < now.date():
            dt = dt.replace(year=year + 1)
        return dt

    def _scrape_detail(self, url: str) -> dict[str, Any] | None:
        """Fetch an event detail page for description, image, and genre tags."""
        resp = self.get(url)
        if not resp:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        result: dict[str, Any] = {}

        # Image: look for og:image or large image in content
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            result["image_url"] = og_img["content"]
        else:
            img = soup.select_one(".event-content img, .page-hero img, .wp-block-image img")
            if img and img.get("src"):
                result["image_url"] = img["src"]

        # Description: main content text
        content = soup.select_one(".event-content, .entry-content, article .content")
        if content:
            desc = content.get_text(" ", strip=True)[:500]
            if len(desc) > 20:
                result["description"] = desc

        # Genre tags: look for genre/tag mentions
        page_text = soup.get_text(" ", strip=True).lower()
        tags = []
        genre_keywords = {
            "rock": "rock", "metal": "metal", "heavy metal": "heavy-metal",
            "hard rock": "hard-rock", "punk": "punk", "pop": "pop",
            "hip hop": "hip-hop", "hip-hop": "hip-hop", "rap": "rap",
            "electronic": "electronic", "techno": "techno", "indie": "indie",
            "jazz": "jazz", "blues": "blues", "soul": "soul", "funk": "funk",
            "reggae": "reggae", "ska": "ska", "folk": "folk", "country": "country",
            "classical": "classical", "singer-songwriter": "singer-songwriter",
            "comedy": "comedy", "kabarett": "comedy", "stand-up": "comedy",
            "schlager": "schlager", "deutsch": "german-language",
        }
        for keyword, tag in genre_keywords.items():
            if keyword in page_text and tag not in tags:
                tags.append(tag)
        if tags:
            result["tags"] = tags

        return result if result else None
