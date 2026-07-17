"""
The Makery Berlin scraper.
Fetches creative workshops (pottery, DJ, candle making, etc.) from themakery.de.

Uses Playwright because the site requires a JS session + AJAX pagination.
Berlin = city ID 9 (default). Workshops are loaded as HTML fragments via AJAX.
Click-based pagination through 25 pages (~900+ workshops).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://themakery.de"
WORKSHOPS_URL = f"{BASE_URL}/workshops/"

# Map Makery categories to NachtKarte categories
CATEGORY_MAP = {
    "kunst": "workshops",
    "kochen": "food",
    "handwerk": "workshops",
    "musik": "music",
    "lifestyle": "workshops",
    "fotografie": "workshops",
    "natur": "outdoors",
    "beauty": "workshops",
    "schreiben": "workshops",
    "sport": "outdoors",
    "textil": "workshops",
}

MONTH_MAP = {
    "jan": 1, "feb": 2, "mär": 3, "mar": 3, "apr": 4,
    "mai": 5, "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "okt": 10, "oct": 10, "nov": 11, "dez": 12, "dec": 12,
}


def _parse_workshop_html(html: str) -> dict[str, Any] | None:
    """Parse a single workshop HTML fragment into a raw event dict."""
    try:
        # URL
        href_match = re.search(r'href="(https://themakery\.de/[^"]+)"', html)
        if not href_match:
            return None
        url = href_match.group(1)

        # Only Berlin workshops
        if not url.endswith("/Berlin"):
            return None

        # Title
        name_match = re.search(
            r'class="name[^"]*"[^>]*>\s*(.+?)\s*</p>', html, re.DOTALL
        )
        title = name_match.group(1).strip() if name_match else None
        if not title:
            return None

        # Makery category
        cat_match = re.search(r'<p class="text-12-16">\s*(\w+)\s*</p>', html)
        makery_cat = cat_match.group(1).strip() if cat_match else ""

        # Price
        price_match = re.search(r'(\d+(?:,\d+)?)\s*€', html)
        price_str = price_match.group(0) if price_match else None
        price_cents = None
        if price_match:
            price_cents = int(float(price_match.group(1).replace(",", ".")) * 100)

        # Duration
        duration_match = re.search(r'(\d+)\s*<span>\s*Min\.\s*</span>', html)
        duration_min = int(duration_match.group(1)) if duration_match else None

        # Next date — "09. Apr." or "09. Apr.   + 571 verfügbare Termine" or "ausgebucht"
        date_match = re.search(r'(\d{1,2})\.\s*(\w{3,4})\.?', html[html.rfind("text-12-16"):] if "text-12-16" in html else html)
        start_time = None
        if date_match:
            day = int(date_match.group(1))
            month_str = date_match.group(2).lower().strip(".")
            month = MONTH_MAP.get(month_str)
            if month:
                now = datetime.now()
                year = now.year
                try:
                    dt = datetime(year, month, day, 10, 0)
                    if dt.date() < now.date():
                        dt = datetime(year + 1, month, day, 10, 0)
                    start_time = dt.isoformat()
                except ValueError:
                    pass

        # Fallback: workshops are bookable anytime — use tomorrow 10:00
        if not start_time:
            from datetime import timedelta
            dt = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
            start_time = dt.isoformat()

        # Neighborhood — appears after "Berlin" tag
        neighborhood = None
        hood_matches = re.findall(
            r'bg-lightgray[^>]*>\s*([^<]+?)\s*</div>', html
        )
        for i, m in enumerate(hood_matches):
            if m.strip() == "Berlin" and i + 1 < len(hood_matches):
                candidate = hood_matches[i + 1].strip()
                if candidate and "★" not in candidate and "Min" not in candidate:
                    neighborhood = candidate
                    break

        # Language
        lang_match = re.search(r'bg-lightgray[^>]*>\s*(Englisch|Deutsch)\s*</div>', html)
        language = lang_match.group(1) if lang_match else None

        # Image
        img_match = re.search(r'src="(https://admin\.themakery\.de/files/[^"]+)"', html)
        image_url = img_match.group(1) if img_match else None

        # Tags
        tags = ["workshop"]
        if language == "Englisch":
            tags.append("english-friendly")
        cat_tag = makery_cat.lower()
        if cat_tag and cat_tag not in tags:
            tags.append(cat_tag)

        category = CATEGORY_MAP.get(cat_tag, "workshops")

        description = title
        if duration_min:
            description += f" ({duration_min} Min.)"
        if language:
            description += f" — {language}"

        return {
            "title": title,
            "venue_name": "The Makery",
            "address": None,
            "neighborhood": neighborhood,
            "start_time": start_time,
            "end_time": None,
            "category": category,
            "subcategory": "creative-workshop",
            "tags": tags,
            "description": description,
            "price": price_str,
            "price_cents": price_cents,
            "image_url": image_url,
            "source_url": url,
        }
    except Exception as e:
        logger.warning("Failed to parse workshop HTML: %s", e)
        return None


class TheMakeryScraper(BaseScraper):
    source_name = "themakery"

    def scrape(self) -> list[dict[str, Any]]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.logger.error("Playwright not installed — skipping The Makery")
            return []

        all_html: list[str] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            page.goto(WORKSHOPS_URL, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)

            # Page 1
            items = page.locator(".workshopitem").all()
            for item in items:
                all_html.append(item.inner_html())
            self.logger.info("Page 1: %d items", len(items))

            # Click through remaining pages
            max_pages = 30
            for pg in range(2, max_pages + 1):
                try:
                    next_btn = page.locator("#page-next")
                    if next_btn.count() == 0:
                        break
                    next_btn.click()
                    page.wait_for_timeout(2000)

                    items = page.locator(".workshopitem").all()
                    if len(items) == 0:
                        break
                    for item in items:
                        all_html.append(item.inner_html())
                    self.logger.info("Page %d: %d items (total: %d)", pg, len(items), len(all_html))
                except Exception as e:
                    self.logger.warning("Pagination stopped at page %d: %s", pg, e)
                    break

            browser.close()

        self.logger.info("Fetched %d raw workshop HTML fragments", len(all_html))

        # Parse listing HTML
        events: list[dict[str, Any]] = []
        for html in all_html:
            parsed = _parse_workshop_html(html)
            if parsed:
                events.append(parsed)

        self.logger.info("Parsed %d Berlin workshops from The Makery", len(events))

        # Enrich with detail pages (description + address)
        self._enrich_from_detail_pages(events)

        return events

    def _enrich_from_detail_pages(self, events: list[dict[str, Any]]) -> None:
        """Fetch detail pages to get descriptions and addresses."""
        import httpx
        import time

        enriched = 0
        for i, event in enumerate(events):
            url = event.get("source_url")
            if not url:
                continue
            try:
                with httpx.Client(timeout=15, follow_redirects=True) as client:
                    resp = client.get(url)
                    if resp.status_code != 200:
                        continue

                html = resp.text

                # Description — look for meta description or long paragraphs
                meta = re.search(r'<meta name="description" content="([^"]+)"', html)
                if meta:
                    event["description"] = meta.group(1).strip()[:500]

                # Address — look for street pattern in text
                addr = re.search(
                    r'(\w[\w\s.-]+(?:Str(?:aße|\.)|straße|weg|platz|allee|damm|ufer)\s*\d+[^,<]{0,30},\s*\d{5}\s*Berlin)',
                    html,
                )
                if addr:
                    event["address"] = addr.group(1).strip()

                enriched += 1
                # Respect rate limits
                if (i + 1) % 10 == 0:
                    self.logger.info("Enriched %d / %d workshops", enriched, len(events))
                    time.sleep(1)

            except Exception as e:
                self.logger.debug("Detail fetch failed for %s: %s", url, e)
                continue

        self.logger.info("Enriched %d / %d workshops with descriptions", enriched, len(events))
