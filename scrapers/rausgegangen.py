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

# Every category rausgegangen actually publishes, with our category as a hint.
#
# This list used to hold FOUR of them. The site has twelve, and they barely
# overlap — 12 categories x 3 pages yielded 1,083 distinct events against 1,152
# fetched, i.e. only 69 duplicates. So the eight missing ones were not redundant
# coverage, they were absent coverage: comedy, exhibitions, film, food and sport
# simply never entered the catalogue.
#
# Found by asking why "Comedy heute Abend?" returned nothing while rausgegangen's
# own site listed eight comedy shows for that evening. All eight sat under
# `shows-und-performances`, which nothing ever fetched. The scraper could parse
# them perfectly the moment it was pointed at the page.
#
# `tickets` and `verlosungen` are deliberately absent — a ticket shop and a raffle
# page, not event listings.
CATEGORY_HINTS: dict[str, str | None] = {
    "konzerte-und-musik": "music",
    "party": "nightlife",
    "shows-und-performances": None,  # comedy, cabaret, drag — let the categorizer decide
    "gesprochenes": None,  # readings, slams, talks
    "theater": "culture",
    "ausstellung": "culture",
    "film": "culture",
    "markt": "markets",
    "food-und-drinks": "food",
    "aktiv-und-kreativ": "workshops",
    "sport": "outdoors",
    "feste-und-festival": None,
}

# Curated pages: small, hand-picked, and worth having even though their events
# also appear under a category.
EDITORIAL_PAGES = [
    f"{BASE_URL}/berlin/tipps-fuer-heute/",
    f"{BASE_URL}/berlin/tipps-fuers-wochenende/",
]

# Listing pages hold 32 events each and paginate with ?page=N. Three pages per
# category is roughly a fortnight of lead time; the pages do not run out at three,
# so this is a deliberate budget rather than exhaustion — raise it when the daily
# run has room.
PAGES_PER_CATEGORY = 3
# Hard ceiling on detail-page fetches per run, so widening the category list can
# never turn into an unbounded scrape.
MAX_EVENT_PAGES = 1500


def _rausgegangen_category_slug(page_url: str) -> str | None:
    """Their own category slug from a listing URL, kept as provenance.

    `.../kategorie/konzerte-und-musik/` -> `rausgegangen:konzerte-und-musik`.
    Namespaced so it never collides with a genre alias; the tips pages carry no
    category and return None.
    """
    parts = [p for p in page_url.split("/") if p]
    if "kategorie" in parts:
        idx = parts.index("kategorie")
        if idx + 1 < len(parts):
            return f"rausgegangen:{parts[idx + 1]}"
    return None


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

    def _listing_urls(self) -> list[tuple[str, str | None]]:
        """(listing url, category hint), categories paginated, editorial pages once."""
        out: list[tuple[str, str | None]] = []
        for slug, hint in CATEGORY_HINTS.items():
            base = f"{BASE_URL}/berlin/kategorie/{slug}/"
            for page in range(1, PAGES_PER_CATEGORY + 1):
                out.append((base if page == 1 else f"{base}?page={page}", hint))
        out.extend((url, None) for url in EDITORIAL_PAGES)
        return out

    def collect_event_urls(self) -> dict[str, tuple[str | None, str | None]]:
        """url -> (category hint, source tag), deduped across categories and pages.

        Separated from scrape() so the listing layer can be tested without fetching
        a thousand detail pages: a silent change in the site's markup shows up here
        as an empty dict, which is exactly the failure that went unnoticed before.
        """
        found: dict[str, tuple[str | None, str | None]] = {}
        for listing_url, hint in self._listing_urls():
            try:
                soup = BeautifulSoup(self.get(listing_url).text, "lxml")
            except Exception as e:  # noqa: BLE001 — one bad page must not stop the rest
                logger.warning("Failed to fetch %s: %s", listing_url, e)
                continue

            urls = self._extract_event_urls_from_jsonld(soup)
            if not urls:
                urls = self._extract_event_urls_from_html(soup)
            if not urls:
                # Loud, because this is how the site changing under us looks.
                logger.warning("rausgegangen: no event URLs on %s", listing_url)
                continue

            tag = _rausgegangen_category_slug(listing_url)
            new = 0
            for url in urls:
                if url not in found:
                    found[url] = (hint, tag)
                    new += 1
            logger.info("rausgegangen: %-52s %3d urls, %3d new", listing_url, len(urls), new)
        return found

    def scrape(self) -> list[dict[str, Any]]:
        found = self.collect_event_urls()
        logger.info("rausgegangen: %d distinct event URLs across all listings", len(found))
        if len(found) > MAX_EVENT_PAGES:
            logger.warning(
                "rausgegangen: capping at %d of %d event pages", MAX_EVENT_PAGES, len(found)
            )

        events = []
        for url, (hint, tag) in list(found.items())[:MAX_EVENT_PAGES]:
            event = self._scrape_event_page(url)
            if not event:
                continue
            if hint and not event.get("category"):
                event["category"] = hint
            # Their category slug is real source metadata; the per-event URL slug
            # we already store is not. Keep both.
            if tag:
                source_tags = event.setdefault("source_tags", [])
                if tag not in source_tags:
                    source_tags.append(tag)
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
