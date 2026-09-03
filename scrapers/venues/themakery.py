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

# The marketplace's own address, in every page footer. Never a workshop location.
MAKERY_HQ_STREET = "John-Schehr-Strasse 2"
# lat_min, lat_max, lng_min, lng_max — a geocode outside this is a wrong match.
BERLIN_BBOX = (52.3, 52.7, 13.0, 13.8)
_PLZ_LINE = re.compile(r"^(\d{5})\s+Berlin$")

# A German house number: 82, 31a, 12-13, 7 - 9.
_HOUSE = r"\d+\s*[a-zA-Z]?(?:\s*[-\u2013]\s*\d+\s*[a-zA-Z]?)?"
# Tokens some listings interleave into the street line. Never part of a street name.
_PLACE_TOKENS = re.compile(r"\b(?:Berlin|Deutschland|Germany|Allemagne|Alemania)\b", re.I)
_TRAILING_DUP = re.compile(rf"\b({_HOUSE})\s+\1\s*$")
_STARTS_WITH_WORDS = re.compile(r"^[^\d]{3,}")
_ENDS_WITH_HOUSE = re.compile(rf"{_HOUSE}\s*$")


def clean_street(line: str) -> str | None:
    """The street part of a studio address line, or None if it is not one.

    The line above the "<5 digits> Berlin" anchor is *usually* just the street, but
    the marketplace's own listings are hand-entered and several shapes reach us:

        "Reutersr. 82, 12053 82"        postcode and house number repeated
        "Reuterstr. , Berlin, Allemagne 82"  city and country interleaved
        "Wrangelstrasse 31a 31a"        house number repeated
        "Golzstrasse  32"               double space

    Concatenating those with ", <plz> Berlin" produced addresses no geocoder would
    accept. The geocode then failed and the event silently inherited the venue's
    coordinates — the marketplace's own studio — so a Neukoelln workshop was drawn
    in Prenzlauer Berg. Returning None is the safe failure: no address beats a
    confident wrong one.
    """
    # Everything from the first postcode onward repeats the anchor we already have.
    s = re.split(r"\b\d{5}\b", line, maxsplit=1)[0]
    s = _PLACE_TOKENS.sub(" ", s)

    # Rebuild from comma-separated parts, dropping the empties the removals leave.
    parts = [re.sub(r"\s+", " ", p).strip() for p in s.split(",")]
    parts = [p for p in parts if p]
    if not parts:
        return None
    # A trailing part that is only a house number belongs to the street before it.
    if len(parts) > 1 and re.fullmatch(_HOUSE, parts[-1]):
        parts[-2:] = [f"{parts[-2]} {parts[-1]}"]
    s = ", ".join(parts)

    s = _TRAILING_DUP.sub(r"\1", s)
    s = re.sub(r"\s+", " ", s).strip(" ,")

    if not (_STARTS_WITH_WORDS.match(s) and _ENDS_WITH_HOUSE.search(s)):
        return None
    return s


def extract_studio_address(html: str) -> str | None:
    """The partner studio's address from a workshop detail page, or None.

    Anchored on the unambiguous "<5 digits> Berlin" line and reading the street
    above it — parsed from TEXT, because street and postcode sit in separate
    elements and any raw-HTML pattern spanning them has to guess at the markup.
    The footer block is skipped by STREET rather than by postcode: real partner
    studios do sit in 10407, and excluding the district would drop them.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    lines = [ln for ln in soup.get_text("\n", strip=True).split("\n") if ln]
    for n, line in enumerate(lines):
        m = _PLZ_LINE.match(line)
        if not m or n < 1:
            continue
        raw_street = lines[n - 1]
        if raw_street == MAKERY_HQ_STREET:
            continue
        street = clean_street(raw_street)
        if street is None:
            logger.warning("Unparseable studio street %r — leaving address unset", raw_street)
            continue
        return f"{street}, {m.group(1)} Berlin"
    return None


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
    "jan": 1,
    "feb": 2,
    "mär": 3,
    "mar": 3,
    "apr": 4,
    "mai": 5,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "okt": 10,
    "oct": 10,
    "nov": 11,
    "dez": 12,
    "dec": 12,
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
        name_match = re.search(r'class="name[^"]*"[^>]*>\s*(.+?)\s*</p>', html, re.DOTALL)
        title = name_match.group(1).strip() if name_match else None
        if not title:
            return None

        # Makery category
        cat_match = re.search(r'<p class="text-12-16">\s*(\w+)\s*</p>', html)
        makery_cat = cat_match.group(1).strip() if cat_match else ""

        # Price
        price_match = re.search(r"(\d+(?:,\d+)?)\s*€", html)
        price_str = price_match.group(0) if price_match else None
        price_cents = None
        if price_match:
            price_cents = int(float(price_match.group(1).replace(",", ".")) * 100)

        # Duration
        duration_match = re.search(r"(\d+)\s*<span>\s*Min\.\s*</span>", html)
        duration_min = int(duration_match.group(1)) if duration_match else None

        # Next date — "09. Apr." or "09. Apr.   + 571 verfügbare Termine" or "ausgebucht"
        date_match = re.search(
            r"(\d{1,2})\.\s*(\w{3,4})\.?",
            html[html.rfind("text-12-16") :] if "text-12-16" in html else html,
        )
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

            dt = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(
                days=1
            )
            start_time = dt.isoformat()

        # Neighborhood — appears after "Berlin" tag
        neighborhood = None
        hood_matches = re.findall(r"bg-lightgray[^>]*>\s*([^<]+?)\s*</div>", html)
        for i, m in enumerate(hood_matches):
            if m.strip() == "Berlin" and i + 1 < len(hood_matches):
                candidate = hood_matches[i + 1].strip()
                if candidate and "★" not in candidate and "Min" not in candidate:
                    neighborhood = candidate
                    break

        # Language
        lang_match = re.search(r"bg-lightgray[^>]*>\s*(Englisch|Deutsch)\s*</div>", html)
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
        """Fetch detail pages for the PARTNER STUDIO's address, and geocode it.

        The Makery is a marketplace, not a venue: every workshop runs at a different
        partner studio. Each detail page carries two addresses — the platform's own
        footer (John-Schehr-Strasse 2, 10407) and the studio's. We want the studio's.

        Two bugs lived here, and together they put every Makery event on one pin:

        1. The address regex ran over raw HTML and forbade `<` between street and
           postcode. On this site they sit in SEPARATE elements, so it could never
           match and `address` stayed None for every workshop. With no address,
           pipeline.geocoder fell through to "The Makery, Berlin" — the company —
           and gave every event the head office in Prenzlauer Berg, while their
           neighborhoods spanned 46 districts. Now we parse text, not markup, and
           anchor on the unambiguous "<5 digits> Berlin" line.

        2. The meta description is the SITE-WIDE marketing blurb, identical on every
           page, and it overwrote the per-workshop description built in
           _parse_workshop. Dropped: a generic string is worse than a short specific
           one, and ~1,200 identical descriptions also collapse into near-identical
           embeddings.

        We geocode here rather than leaving it to pipeline.geocoder because that
        function resolves the VENUE NAME against the venues table first, which for
        this source always wins and always yields the marketplace's head office.
        Emitting coordinates means those events are already resolved and the
        venue-name shortcut never runs. Geocodes are cached per address — the ~700
        workshops share far fewer studios.
        """
        import time

        import httpx

        from pipeline.geocoder import geocode

        geo_cache: dict[str, tuple[float, float] | None] = {}
        found_addr = 0

        for i, event in enumerate(events):
            url = event.get("source_url")
            if not url:
                continue
            try:
                with httpx.Client(timeout=15, follow_redirects=True) as client:
                    resp = client.get(url)
                    if resp.status_code != 200:
                        continue

                addr = extract_studio_address(resp.text)
                if addr:
                    event["address"] = addr
                    found_addr += 1

                if addr:
                    if addr not in geo_cache:
                        geo_cache[addr] = geocode(f"{addr}, Germany")
                        time.sleep(1)  # Nominatim usage policy
                    hit = geo_cache[addr]
                    # A hit outside Berlin is a mismatch, not a location — leave the
                    # event uncoordinated rather than pin it somewhere wrong.
                    if (
                        hit
                        and BERLIN_BBOX[0] <= hit[0] <= BERLIN_BBOX[1]
                        and BERLIN_BBOX[2] <= hit[1] <= BERLIN_BBOX[3]
                    ):
                        event["lat"], event["lng"] = hit

                if (i + 1) % 10 == 0:
                    self.logger.info("Enriched %d / %d workshops", found_addr, len(events))
                    time.sleep(1)

            except Exception as e:
                self.logger.debug("Detail fetch failed for %s: %s", url, e)
                continue

        located = sum(1 for e in events if e.get("lat"))
        self.logger.info(
            "Enriched %d / %d workshops with a studio address, %d geocoded (%d distinct)",
            found_addr,
            len(events),
            located,
            len(geo_cache),
        )
