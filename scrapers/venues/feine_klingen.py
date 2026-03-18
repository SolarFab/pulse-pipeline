"""
feine-klingen.de scraper — blacksmithing & knife-making workshops in Neukölln.

Scrapes WooCommerce product category page for courses.
Dates and times are embedded in product titles.
2-day courses without explicit times default to 10:00.
"""

from __future__ import annotations

import logging
import re
from html import unescape
from typing import Any

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.feine-klingen.de"
CATEGORY_URL = f"{BASE_URL}/produkt-kategorie/kurs/"

VENUE_NAME = "Rixdorfer Schmiede – Feine Klingen"
VENUE_ADDRESS = "Richardstraße 100, 12043 Berlin"
VENUE_LAT = 52.4753
VENUE_LNG = 13.4470

_STRIP_HTML = re.compile(r"<[^>]+>")

# German month names → number
_MONTHS = {
    "januar": "01", "februar": "02", "märz": "03", "maerz": "03",
    "april": "04", "mai": "05", "juni": "06", "juli": "07",
    "august": "08", "september": "09", "oktober": "10",
    "november": "11", "dezember": "12",
}


class FeineKlingenScraper(BaseScraper):
    source_name = "feine_klingen"

    def scrape(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        # Fetch all pages
        page = 1
        while True:
            url = CATEGORY_URL if page == 1 else f"{CATEGORY_URL}page/{page}/"
            try:
                resp = self.get(url)
            except Exception:
                break

            html = resp.text
            page_events = self._parse_page(html)
            if not page_events:
                break

            events.extend(page_events)
            page += 1

            # Safety limit
            if page > 5:
                break

        logger.info("feine_klingen: extracted %d workshop events", len(events))
        return events

    def _parse_page(self, html: str) -> list[dict[str, Any]]:
        """Parse product listing page for workshop events."""
        events = []

        # Find product items — WooCommerce uses <li class="product ...">
        # Extract title and price from each product block
        product_pattern = re.compile(
            r'<li[^>]*class="[^"]*product[^"]*"[^>]*>.*?'
            r'<a[^>]+href="([^"]+)"[^>]*>.*?'
            r'<h2[^>]*class="[^"]*woocommerce-loop-product__title[^"]*"[^>]*>(.*?)</h2>.*?'
            r'(?:<span[^>]*class="[^"]*woocommerce-Price-amount[^"]*"[^>]*>.*?(\d[\d.,]*)\s*€.*?)?'
            r'</li>',
            re.DOTALL,
        )

        # Simpler approach: find all product links and titles
        # WooCommerce product titles in <h2 class="woocommerce-loop-product__title">
        title_pattern = re.compile(
            r'<a[^>]+href="(https://www\.feine-klingen\.de/produkt/[^"]+)"[^>]*>\s*'
            r'<img[^>]*>.*?'
            r'<h2[^>]*>(.*?)</h2>',
            re.DOTALL,
        )

        price_pattern = re.compile(
            r'<span class="woocommerce-Price-amount amount">'
            r'<bdi>([\d.,]+)\s*(?:&nbsp;)?<span[^>]*>(?:€|&euro;)</span></bdi></span>',
        )

        # Split HTML into product blocks
        blocks = re.split(r'<li[^>]*class="[^"]*product\s', html)

        for block in blocks[1:]:  # skip first (before any product)
            # Extract URL and title
            link_match = re.search(
                r'<a[^>]+href="(https://www\.feine-klingen\.de/produkt/[^"]+)"', block
            )
            title_match = re.search(
                r'<h2[^>]*class="[^"]*woocommerce-loop-product__title[^"]*"[^>]*>(.*?)</h2>',
                block, re.DOTALL,
            )

            if not link_match or not title_match:
                continue

            url = link_match.group(1)
            title = _strip_html(title_match.group(1)).strip()

            # Skip gift vouchers
            if "gutschein" in title.lower():
                continue

            # Clean title — remove "AUSGEBUCHT!" prefix
            title = re.sub(r"^AUSGEBUCHT!\s*", "", title).strip()

            # Extract price (first match)
            prices = price_pattern.findall(block)
            price_str = None
            if prices:
                price_str = f"€{prices[0].replace(',', '.')}"

            # Parse date and time from title
            parsed = self._parse_title(title)
            if not parsed:
                continue

            start_time, end_time = parsed

            # Check sold out
            sold_out = "ausgebucht" in block.lower()

            # Extract image
            img_match = re.search(r'<img[^>]+src="([^"]+)"', block)
            image_url = img_match.group(1) if img_match else None

            # Determine workshop type for description
            description = self._get_description(title)

            events.append({
                "title": title,
                "venue_name": VENUE_NAME,
                "address": VENUE_ADDRESS,
                "lat": VENUE_LAT,
                "lng": VENUE_LNG,
                "start_time": start_time,
                "end_time": end_time,
                "description": description,
                "price": f"{price_str} (ausgebucht)" if sold_out and price_str else price_str,
                "source_url": url,
                "source_id": f"feineklingen-{title[:50]}-{start_time[:10]}",
                "category": "workshops",
                "subcategory": "craft",
                "tags": ["blacksmithing", "craft", "neukölln"],
                "image_url": image_url,
                "source": self.source_name,
            })

        return events

    def _parse_title(self, title: str) -> tuple[str, str | None] | None:
        """Extract start_time and end_time from workshop title.

        Examples:
          "Workshop Messer schleifen – 15. April 2026 um 18 Uhr"
          "Messerschmiedekurs Ganzstahlmesser – 21. und 22. März 2026"
          "Grundkurs Schmieden – 7. Mai 2026 um 17 Uhr"
        """
        title_lower = title.lower()

        # Try: "DD. Monat YYYY um HH Uhr"
        single_match = re.search(
            r"(\d{1,2})\.\s*(\w+)\s+(\d{4})\s+um\s+(\d{1,2})\s*uhr",
            title_lower,
        )
        if single_match:
            day, month_name, year, hour = single_match.groups()
            month = _MONTHS.get(month_name)
            if not month:
                return None
            start = f"{year}-{month}-{day.zfill(2)}T{hour.zfill(2)}:00:00"
            return start, None

        # Try: "DD. und DD. Monat YYYY" (2-day course)
        range_match = re.search(
            r"(\d{1,2})\.\s*und\s+(\d{1,2})\.\s*(\w+)\s+(\d{4})",
            title_lower,
        )
        if range_match:
            day1, day2, month_name, year = range_match.groups()
            month = _MONTHS.get(month_name)
            if not month:
                return None
            # Default to 10:00 for full-day workshops
            start = f"{year}-{month}-{day1.zfill(2)}T10:00:00"
            end = f"{year}-{month}-{day2.zfill(2)}T18:00:00"
            return start, end

        # Try: just "DD. Monat YYYY"
        date_match = re.search(
            r"(\d{1,2})\.\s*(\w+)\s+(\d{4})",
            title_lower,
        )
        if date_match:
            day, month_name, year = date_match.groups()
            month = _MONTHS.get(month_name)
            if not month:
                return None
            start = f"{year}-{month}-{day.zfill(2)}T10:00:00"
            return start, None

        return None

    def _get_description(self, title: str) -> str:
        """Generate description based on workshop type."""
        tl = title.lower()
        if "messer schleifen" in tl:
            return (
                "Lerne in diesem Workshop, wie du deine Messer richtig schärfst. "
                "Bring deine eigenen Messer mit und lerne professionelle Schleiftechniken "
                "in der Rixdorfer Schmiede in Neukölln."
            )
        if "ganzstahlmesser" in tl:
            return (
                "Zweitägiger Messerschmiedekurs: Schmiede dein eigenes Ganzstahlmesser "
                "von Grund auf. Du lernst alle Schritte vom Rohling bis zum fertigen Messer "
                "in der Rixdorfer Schmiede."
            )
        if "holzgriff" in tl:
            return (
                "Zweitägiger Messerschmiedekurs: Schmiede dein eigenes Messer mit Holzgriff. "
                "Vom Stahl schmieden über Härten bis zum Griffmontage — "
                "alles in der Rixdorfer Schmiede in Neukölln."
            )
        if "axtschmiede" in tl:
            return (
                "Zweitägiger Axtschmiedekurs: Schmiede deine eigene Axt von Grund auf. "
                "Traditionelle Schmiedetechniken in der Rixdorfer Schmiede in Neukölln."
            )
        if "grundkurs" in tl:
            return (
                "Grundkurs Schmieden: Dein Einstieg in die Welt des Schmiedens. "
                "Lerne die Basics an Amboss und Esse in der Rixdorfer Schmiede."
            )
        if "workshop schmieden" in tl:
            return (
                "Ganztägiger Schmiedeworkshop in der Rixdorfer Schmiede. "
                "Intensive Einführung in traditionelle Schmiedetechniken in Neukölln."
            )
        return "Schmiedeworkshop in der Rixdorfer Schmiede, Neukölln."


def _strip_html(text: str) -> str:
    return unescape(_STRIP_HTML.sub("", text)).strip()
