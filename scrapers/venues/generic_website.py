"""
Generic venue website scraper.

Instead of writing per-venue HTML parsers, this scraper:
1. Reads venue_sources.json for venues that have a "website" source
2. Fetches each venue's events page
3. Uses Claude to extract structured event data from the raw HTML
4. Returns standard RawEvent dicts

One scraper, many venues — no custom parsing logic needed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SOURCES_PATH = Path(__file__).parent.parent.parent / "data" / "venue_sources.json"

# Content-hash cache: venue URL -> sha256 of the cleaned events page.
# Unchanged pages skip extraction entirely (their events are already in the
# DB from the previous run) — this cuts 80-90% of LLM calls on daily runs.
CACHE_PATH = Path(__file__).parent.parent.parent / "data" / "scrape_cache.json"

EXTRACTION_PROMPT_TEMPLATE = (
    "You are an event extraction assistant. Given raw HTML from a Berlin venue's events page, "
    "extract ALL upcoming events into structured JSON.\n\n"
    "For each event found, return:\n"
    '{"title": "Event title", "start_time": "ISO 8601 datetime (YYYY-MM-DDTHH:MM:SS) in Berlin time, '
    'or YYYY-MM-DD if no time", "end_time": "ISO 8601 or null", "description": "Short description '
    '(max 300 chars) or null", "price": "e.g. \'€12\', \'Free\', \'€8-15\', or null", '
    '"image_url": "absolute URL or null", "source_url": "event detail URL if available, or null"}\n\n'
    "Rules:\n"
    "- Extract ONLY future events (today or later). Current date: TODAY_PLACEHOLDER.\n"
    "- Parse German dates: \"Fr. 18. April\", \"18.04.2026\", \"Freitag, 18. April 2026\" etc.\n"
    "- Parse German times: \"Einlass 20:00, Beginn 21:00\" → start_time uses Beginn, \"Türen 22h\" → 22:00\n"
    "- If only a date with no time is given, omit the time portion (just YYYY-MM-DD).\n"
    "- Prices: \"Eintritt frei\" / \"kostenlos\" → \"Free\", \"VVK €12 / AK €15\" → \"€12-15\", \"ab 8€\" → \"from €8\"\n"
    "- Image URLs must be absolute (start with http). Convert relative paths using the page's base URL.\n"
    "- Skip past events, recurring schedule descriptions, and non-event content (menus, about pages).\n"
    "- If the HTML contains NO events, return an empty array [].\n\n"
    "Return ONLY a JSON array. No explanation."
)


class GenericWebsiteScraper(BaseScraper):
    source_name = "venue_website"

    def __init__(self):
        super().__init__()
        self._venues = self._load_venues()
        self._client: anthropic.Anthropic | None = None

    def _load_venues(self) -> list[dict[str, Any]]:
        """Load venues that have a website source from venue_sources.json."""
        if not SOURCES_PATH.exists():
            logger.error("venue_sources.json not found at %s", SOURCES_PATH)
            return []

        with open(SOURCES_PATH) as f:
            all_venues = json.load(f)

        venues = []
        for name, config in all_venues.items():
            sources = config.get("sources", {})
            if "website" in sources:
                venues.append({
                    "name": name,
                    "url": sources["website"],
                    "lat": config.get("lat"),
                    "lng": config.get("lng"),
                    "address": config.get("address"),
                    "neighborhood": config.get("neighborhood", "Neukölln"),
                })
        return venues

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError("ANTHROPIC_API_KEY not set")
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def scrape(self) -> list[dict[str, Any]]:
        all_events: list[dict[str, Any]] = []
        cache = self._load_cache()

        for venue in self._venues:
            try:
                events = self._scrape_venue(venue, cache)
                all_events.extend(events)
                logger.info("%s: %d events", venue["name"], len(events))
            except Exception as e:
                logger.warning("Failed to scrape %s (%s): %s", venue["name"], venue["url"], e)

        self._save_cache(cache)
        logger.info("generic_website: %d total events from %d venues", len(all_events), len(self._venues))
        return all_events

    def _load_cache(self) -> dict[str, Any]:
        if CACHE_PATH.exists():
            try:
                with open(CACHE_PATH) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_cache(self, cache: dict[str, Any]) -> None:
        CACHE_PATH.parent.mkdir(exist_ok=True)
        with open(CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False, sort_keys=True)

    def _scrape_venue(self, venue: dict[str, Any], cache: dict[str, Any]) -> list[dict[str, Any]]:
        """Fetch a venue's events page and extract events (cheapest method first)."""
        url = venue["url"]

        # Fetch HTML
        resp = self.get(url)
        html = resp.text

        # Trim HTML to reduce tokens — strip scripts, styles, nav, footer
        html_clean = self._clean_html(html)

        # Change detection: unchanged page → events already upserted last run
        content_hash = hashlib.sha256(html_clean.encode()).hexdigest()
        cached = cache.get(url)
        if cached and cached.get("hash") == content_hash:
            logger.info("%s: page unchanged, skipping extraction", venue["name"])
            return []
        cache[url] = {"hash": content_hash, "checked_at": datetime.now().isoformat(timespec="seconds")}

        # Layer 1: schema.org JSON-LD — deterministic, free, no hallucination risk
        raw_events = self._extract_jsonld_events(html, url)
        if raw_events:
            logger.info("%s: %d events via JSON-LD (no LLM needed)", venue["name"], len(raw_events))
        else:
            # Layer 2: LLM extraction
            if len(html_clean) > 30_000:
                html_clean = html_clean[:30_000] + "\n<!-- truncated -->"
            raw_events = self._extract_events(html_clean, url, venue)

        # Attach venue metadata
        events = []
        for raw in raw_events:
            events.append({
                "title": raw.get("title", "").strip(),
                "venue_name": venue["name"],
                "lat": venue.get("lat"),
                "lng": venue.get("lng"),
                "address": venue.get("address"),
                "neighborhood": venue.get("neighborhood", "Neukölln"),
                "start_time": raw.get("start_time"),
                "end_time": raw.get("end_time"),
                "description": raw.get("description"),
                "price": raw.get("price"),
                "image_url": raw.get("image_url"),
                "source_url": raw.get("source_url") or url,
                "source_id": f"{venue['name']}_{raw.get('start_time', '')}_{raw.get('title', '')[:30]}",
                "source": self.source_name,
            })

        return events

    def _extract_jsonld_events(self, html: str, page_url: str) -> list[dict[str, Any]]:
        """Parse schema.org Event JSON-LD blocks — many venue sites (WordPress,
        Squarespace, ticketing widgets) embed them, making LLM extraction
        unnecessary."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        events: list[dict[str, Any]] = []
        today = datetime.now().strftime("%Y-%m-%d")

        def walk(node: Any) -> None:
            if isinstance(node, list):
                for item in node:
                    walk(item)
                return
            if not isinstance(node, dict):
                return
            if "@graph" in node:
                walk(node["@graph"])
            node_type = node.get("@type", "")
            types = node_type if isinstance(node_type, list) else [node_type]
            if not any(isinstance(t, str) and t.endswith("Event") for t in types):
                return
            start = node.get("startDate")
            title = node.get("name")
            if not start or not title:
                return
            if str(start)[:10] < today:
                return  # past event
            location = node.get("location") or {}
            if isinstance(location, list):
                location = location[0] if location else {}
            offers = node.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price = offers.get("price")
            image = node.get("image")
            if isinstance(image, list):
                image = image[0] if image else None
            if isinstance(image, dict):
                image = image.get("url")
            events.append({
                "title": str(title).strip(),
                "start_time": start,
                "end_time": node.get("endDate"),
                "description": (node.get("description") or "")[:300] or None,
                "price": f"€{price}" if price not in (None, "", "0", 0) else None,
                "image_url": urljoin(page_url, image) if image else None,
                "source_url": urljoin(page_url, node["url"]) if node.get("url") else None,
            })

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                walk(json.loads(script.string or ""))
            except (json.JSONDecodeError, TypeError):
                continue

        return events

    def _clean_html(self, html: str) -> str:
        """Strip non-content HTML to reduce token count."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")

        # Remove elements that never contain event data
        for tag in soup.find_all(["script", "style", "noscript", "iframe", "svg", "path"]):
            tag.decompose()
        for tag in soup.find_all(["nav", "footer", "header"]):
            tag.decompose()
        # Remove hidden elements
        for tag in soup.find_all(style=lambda s: s and "display:none" in s.replace(" ", "")):
            tag.decompose()

        # Get text-bearing HTML (main/article/section preferred)
        main = soup.find("main") or soup.find("article") or soup.find("body")
        return str(main) if main else str(soup)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _extract_events(self, html: str, page_url: str, venue: dict) -> list[dict]:
        """Use Claude to extract events from HTML."""
        client = self._get_client()
        today = datetime.now().strftime("%Y-%m-%d")

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system=[{
                "type": "text",
                "text": EXTRACTION_PROMPT_TEMPLATE.replace("TODAY_PLACEHOLDER", today),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": (
                    f"Venue: {venue['name']}\n"
                    f"Page URL: {page_url}\n\n"
                    f"HTML:\n{html}"
                ),
            }],
        )

        raw = message.content[0].text.strip()
        # Strip markdown code fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        results = json.loads(raw)
        if not isinstance(results, list):
            results = [results] if results else []

        return results
