"""
Bandsintown scraper for Berlin music venues.

Strategy:
1. Try the Bandsintown public artist-events API for each known Berlin venue.
2. Fall back to scraping the Bandsintown venue/artist pages if the API fails.

Covers jazz clubs, live music venues, and concert halls across Berlin.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Bandsintown public API base — the app_id can be any non-empty string.
API_BASE = "https://rest.bandsintown.com"
APP_ID = "whatsupp"

# Known Berlin music venues with their Bandsintown slugs (or search names)
# and coordinates for geocoding fallback.
BERLIN_VENUES: list[dict[str, Any]] = [
    {
        "name": "Zigzag Jazz Club",
        "slug": "zigzag-jazz-club",
        "lat": 52.4862,
        "lng": 13.3529,
        "address": "Hauptstraße 12, 10827 Berlin",
        "neighborhood": "Schöneberg",
        "genre_hint": "jazz",
    },
    {
        "name": "A-Trane",
        "slug": "a-trane",
        "lat": 52.5072,
        "lng": 13.3226,
        "address": "Bleibtreustraße 1, 10623 Berlin",
        "neighborhood": "Charlottenburg",
        "genre_hint": "jazz",
    },
    {
        "name": "B-flat",
        "slug": "b-flat",
        "lat": 52.5254,
        "lng": 13.3883,
        "address": "Dircksenstraße 40, 10178 Berlin",
        "neighborhood": "Mitte",
        "genre_hint": "jazz",
    },
    {
        "name": "Quasimodo",
        "slug": "quasimodo",
        "lat": 52.5042,
        "lng": 13.3271,
        "address": "Kantstraße 12a, 10623 Berlin",
        "neighborhood": "Charlottenburg",
        "genre_hint": "jazz",
    },
    {
        "name": "Lido Berlin",
        "slug": "lido-berlin",
        "lat": 52.4955,
        "lng": 13.4310,
        "address": "Cuvrystraße 7, 10997 Berlin",
        "neighborhood": "Kreuzberg",
        "genre_hint": "indie",
    },
    {
        "name": "SO36",
        "slug": "so36",
        "lat": 52.4990,
        "lng": 13.4340,
        "address": "Oranienstraße 190, 10999 Berlin",
        "neighborhood": "Kreuzberg",
        "genre_hint": "punk",
    },
    {
        "name": "Bi Nuu",
        "slug": "bi-nuu",
        "lat": 52.4956,
        "lng": 13.4399,
        "address": "Schlesische Straße 31, 10997 Berlin",
        "neighborhood": "Kreuzberg",
        "genre_hint": "indie",
    },
    {
        "name": "Festsaal Kreuzberg",
        "slug": "festsaal-kreuzberg",
        "lat": 52.4901,
        "lng": 13.4350,
        "address": "Skalitzer Straße 130, 10999 Berlin",
        "neighborhood": "Kreuzberg",
        "genre_hint": "indie",
    },
    {
        "name": "Hole44",
        "slug": "hole44",
        "lat": 52.4865,
        "lng": 13.4240,
        "address": "Hermannstraße 44, 12049 Berlin",
        "neighborhood": "Neukölln",
        "genre_hint": "rock",
    },
    {
        "name": "Privatclub",
        "slug": "privatclub",
        "lat": 52.5003,
        "lng": 13.4395,
        "address": "Skalitzer Straße 99, 10997 Berlin",
        "neighborhood": "Kreuzberg",
        "genre_hint": "indie",
    },
]

# Map genre keywords found in tags/descriptions to our standardized subcategories.
GENRE_KEYWORDS: dict[str, str] = {
    "jazz": "jazz-blues",
    "blues": "jazz-blues",
    "soul": "jazz-blues",
    "funk": "jazz-blues",
    "r&b": "jazz-blues",
    "hip hop": "hip-hop",
    "hip-hop": "hip-hop",
    "rap": "hip-hop",
    "electronic": "electronic",
    "techno": "electronic",
    "house": "electronic",
    "dnb": "electronic",
    "drum and bass": "electronic",
    "ambient": "electronic",
    "rock": "rock-pop",
    "metal": "rock-pop",
    "punk": "rock-pop",
    "hardcore": "rock-pop",
    "indie": "rock-pop",
    "alternative": "rock-pop",
    "pop": "rock-pop",
    "singer-songwriter": "rock-pop",
    "folk": "world-folk",
    "country": "world-folk",
    "reggae": "world-folk",
    "ska": "world-folk",
    "latin": "latin",
    "salsa": "latin",
    "cumbia": "latin",
    "classical": "classical",
    "world": "world-folk",
}


class BandsintownScraper(BaseScraper):
    source_name = "bandsintown"

    def scrape(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        for venue in BERLIN_VENUES:
            venue_events = self._scrape_venue(venue)
            events.extend(venue_events)

        # Deduplicate by source_id
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for ev in events:
            sid = ev.get("source_id", "")
            if sid and sid not in seen:
                seen.add(sid)
                unique.append(ev)
            elif not sid:
                unique.append(ev)

        logger.info("bandsintown: scraped %d unique events across %d venues",
                     len(unique), len(BERLIN_VENUES))
        return unique

    # ── Per-venue scraping ────────────────────────────────────────────────

    def _scrape_venue(self, venue: dict[str, Any]) -> list[dict[str, Any]]:
        """Try multiple Bandsintown endpoints for a single venue."""
        slug = venue["slug"]
        name = venue["name"]

        # Strategy 1: venue search via artist-style endpoint
        # Bandsintown treats venues similarly — try the slug as an artist name.
        events = self._try_artist_events_api(slug, venue)
        if events:
            logger.info("  %s: got %d events via artist API", name, len(events))
            return events

        # Strategy 2: try with the full venue name (URL-encoded by httpx)
        events = self._try_artist_events_api(name, venue)
        if events:
            logger.info("  %s: got %d events via name lookup", name, len(events))
            return events

        # Strategy 3: scrape the Bandsintown venue HTML page
        events = self._try_venue_page(slug, venue)
        if events:
            logger.info("  %s: got %d events via venue page", name, len(events))
            return events

        logger.debug("  %s: no events found", name)
        return []

    def _try_artist_events_api(
        self, artist_or_venue: str, venue: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """
        Hit /artists/{name}/events — works for both artists and some venues.
        Returns parsed event dicts or empty list on failure.
        """
        url = f"{API_BASE}/artists/{artist_or_venue}/events"
        try:
            data = self.get_json(
                url,
                params={"app_id": APP_ID, "date": "upcoming"},
                headers={"Accept": "application/json"},
            )
        except Exception:
            return []

        if not isinstance(data, list):
            return []

        results: list[dict[str, Any]] = []
        for item in data:
            parsed = self._parse_api_event(item, venue)
            if parsed:
                results.append(parsed)
        return results

    def _try_venue_page(
        self, slug: str, venue: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """
        Scrape the public Bandsintown venue page for upcoming events.
        Falls back to HTML parsing with regex for the JSON-LD or
        Next.js __NEXT_DATA__ payload that Bandsintown embeds.
        """
        url = f"https://www.bandsintown.com/v/{slug}"
        try:
            resp = self.get(url, headers={"Accept": "text/html"})
            html = resp.text
        except Exception:
            # Try alternate URL pattern
            try:
                url = f"https://www.bandsintown.com/venue/{slug}"
                resp = self.get(url, headers={"Accept": "text/html"})
                html = resp.text
            except Exception:
                return []

        return self._parse_venue_html(html, venue)

    # ── Parsing helpers ───────────────────────────────────────────────────

    def _parse_api_event(
        self, item: dict[str, Any], venue_info: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Parse a single event from the Bandsintown JSON API response."""
        try:
            # Artist info
            artist_name = ""
            if isinstance(item.get("artist"), dict):
                artist_name = item["artist"].get("name", "")
            elif isinstance(item.get("lineup"), list) and item["lineup"]:
                artist_name = item["lineup"][0]

            title = item.get("title", "").strip() or artist_name.strip()
            if not title:
                return None

            # Lineup for description
            lineup = item.get("lineup") or []
            if isinstance(lineup, list) and len(lineup) > 1:
                description = f"Lineup: {', '.join(lineup[:10])}"
            elif artist_name:
                description = artist_name
            else:
                description = None

            # Venue — prefer API data, fall back to our known info
            api_venue = item.get("venue") or {}
            venue_name = (
                api_venue.get("name", "").strip()
                or venue_info["name"]
            )
            address = (
                api_venue.get("street_address")
                or api_venue.get("location", "")
                or venue_info.get("address")
            )
            lat = _safe_float(api_venue.get("latitude")) or venue_info.get("lat")
            lng = _safe_float(api_venue.get("longitude")) or venue_info.get("lng")
            city = api_venue.get("city", "Berlin")
            region = api_venue.get("region", "")

            # Filter: only keep Berlin events (the API might return worldwide)
            if city and "berlin" not in city.lower() and region and "berlin" not in region.lower():
                return None

            # Times
            start_time = item.get("datetime") or item.get("starts_at")
            end_time = item.get("ends_at")

            # Links
            source_url = item.get("url") or item.get("artist", {}).get("url")
            source_id = str(item.get("id", ""))

            # Image
            image_url = (
                item.get("artist", {}).get("image_url")
                or item.get("image_url")
            )
            # Bandsintown sometimes returns a placeholder — skip those
            if image_url and "default" in image_url and "s_" in image_url:
                image_url = None

            # Offers / price
            offers = item.get("offers") or []
            price = self._extract_price(offers)

            # Subcategory from tags or genre hint
            tags = item.get("tags") or []
            artist_tags = item.get("artist", {}).get("tags") or [] if isinstance(item.get("artist"), dict) else []
            all_tags = tags + artist_tags
            subcategory = _infer_subcategory(all_tags, title, venue_info.get("genre_hint"))

            return {
                "title": title,
                "venue_name": venue_name,
                "address": address,
                "neighborhood": venue_info.get("neighborhood"),
                "lat": lat,
                "lng": lng,
                "start_time": start_time,
                "end_time": end_time,
                "description": description,
                "price": price,
                "image_url": image_url,
                "source_url": source_url,
                "source_id": source_id,
                "category": "music",
                "subcategory": subcategory,
                "tags": _build_tags(all_tags, subcategory),
                "source_tags": all_tags if all_tags else [],
                "source": self.source_name,
            }
        except Exception as e:
            logger.debug("bandsintown event parse error: %s", e)
            return None

    def _parse_venue_html(
        self, html: str, venue_info: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """
        Extract events from Bandsintown venue HTML page.
        Looks for __NEXT_DATA__ JSON blob or falls back to
        structured data (JSON-LD) in <script> tags.
        """
        import json

        events: list[dict[str, Any]] = []

        # Attempt 1: __NEXT_DATA__ (Next.js SSR payload)
        next_data_match = re.search(
            r'<script\s+id="__NEXT_DATA__"\s+type="application/json">\s*({.+?})\s*</script>',
            html,
            re.DOTALL,
        )
        if next_data_match:
            try:
                payload = json.loads(next_data_match.group(1))
                events = self._extract_from_next_data(payload, venue_info)
                if events:
                    return events
            except json.JSONDecodeError:
                pass

        # Attempt 2: JSON-LD structured data
        jsonld_matches = re.findall(
            r'<script\s+type="application/ld\+json">\s*({.+?})\s*</script>',
            html,
            re.DOTALL,
        )
        for blob in jsonld_matches:
            try:
                ld = json.loads(blob)
                parsed = self._parse_jsonld_event(ld, venue_info)
                if parsed:
                    events.append(parsed)
            except json.JSONDecodeError:
                continue

        return events

    def _extract_from_next_data(
        self, payload: dict[str, Any], venue_info: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Walk the __NEXT_DATA__ tree looking for event objects."""
        events: list[dict[str, Any]] = []

        # The structure varies, but events are typically under
        # props.pageProps.events or similar.
        page_props = payload.get("props", {}).get("pageProps", {})
        raw_events = (
            page_props.get("events")
            or page_props.get("upcomingEvents")
            or page_props.get("data", {}).get("events")
            or []
        )

        for item in raw_events:
            parsed = self._parse_api_event(item, venue_info)
            if parsed:
                events.append(parsed)

        return events

    def _parse_jsonld_event(
        self, ld: dict[str, Any], venue_info: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Parse a schema.org/MusicEvent JSON-LD object."""
        ld_type = ld.get("@type", "")
        if ld_type not in ("MusicEvent", "Event"):
            return None

        try:
            title = ld.get("name", "").strip()
            if not title:
                return None

            location = ld.get("location") or {}
            venue_name = location.get("name") or venue_info["name"]
            address_obj = location.get("address") or {}
            if isinstance(address_obj, str):
                address = address_obj
            else:
                address = address_obj.get("streetAddress") or venue_info.get("address")

            geo = location.get("geo") or {}
            lat = _safe_float(geo.get("latitude")) or venue_info.get("lat")
            lng = _safe_float(geo.get("longitude")) or venue_info.get("lng")

            start_time = ld.get("startDate")
            end_time = ld.get("endDate")
            description = ld.get("description")
            image_url = ld.get("image")
            source_url = ld.get("url")

            offers = ld.get("offers") or {}
            if isinstance(offers, dict):
                price_val = offers.get("price")
                currency = offers.get("priceCurrency", "EUR")
                price = f"{price_val} {currency}" if price_val else None
            else:
                price = None

            subcategory = _infer_subcategory([], title, venue_info.get("genre_hint"))

            return {
                "title": title,
                "venue_name": venue_name,
                "address": address,
                "neighborhood": venue_info.get("neighborhood"),
                "lat": lat,
                "lng": lng,
                "start_time": start_time,
                "end_time": end_time,
                "description": description,
                "price": price,
                "image_url": image_url,
                "source_url": source_url,
                "source_id": None,
                "category": "music",
                "subcategory": subcategory,
                "tags": _build_tags([], subcategory),
                "source_tags": [],
                "source": self.source_name,
            }
        except Exception as e:
            logger.debug("JSON-LD parse error: %s", e)
            return None

    @staticmethod
    def _extract_price(offers: list[dict[str, Any]]) -> str | None:
        """Pull a human-readable price string from Bandsintown offers."""
        if not offers:
            return None
        for offer in offers:
            status = offer.get("status", "").lower()
            if status == "free":
                return "Free"
            url = offer.get("url", "")
            # Bandsintown often just links out; no price in the API.
            # Check for a "type" field.
            offer_type = offer.get("type", "")
            if offer_type:
                return offer_type.replace("_", " ").title()
        return None


# ── Module-level helpers ─────────────────────────────────────────────────


def _safe_float(val: Any) -> float | None:
    """Convert a value to float, returning None on failure."""
    if val is None:
        return None
    try:
        f = float(val)
        # Bandsintown sometimes returns 0.0 for unknown coords
        return f if f != 0.0 else None
    except (TypeError, ValueError):
        return None


def _infer_subcategory(
    tags: list[str], title: str, genre_hint: str | None
) -> str:
    """Guess a music subcategory from tags, title text, or venue hint."""
    combined = " ".join(tags).lower() + " " + title.lower()
    for keyword, genre in GENRE_KEYWORDS.items():
        if keyword in combined:
            return genre
    # Fall back to venue's default genre hint
    return genre_hint or "live-music"


def _build_tags(raw_tags: list[str], subcategory: str) -> list[str]:
    """Build a clean tag list for the event."""
    base = {"music", "live-music"}
    if subcategory:
        base.add(subcategory)
    for tag in raw_tags:
        cleaned = tag.strip().lower()
        if cleaned and len(cleaned) < 40:
            base.add(cleaned)
    return sorted(base)
