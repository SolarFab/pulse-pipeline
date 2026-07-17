"""
Instagram venue event scraper (via Apify).

For venues that only post events on Instagram, this scraper:
1. Reads venue_sources.json for venues with an "instagram" source
2. Fetches recent posts via Apify's Instagram scraper (no IG login needed)
3. Uses Claude to identify which posts are event announcements
4. Extracts structured event data from those posts

Skips venues that already have a "website" or "ra" source (those are
handled by the generic_website scraper or RA scraper).

Requires APIFY_TOKEN in .env.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import anthropic
from apify_client import ApifyClient
from tenacity import retry, stop_after_attempt, wait_exponential

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SOURCES_PATH = Path(__file__).parent.parent.parent / "data" / "venue_sources.json"

# How many recent posts to check per venue
MAX_POSTS_PER_VENUE = 12

# Only look at posts from the last N days
POST_AGE_LIMIT_DAYS = 30

# Apify actor for Instagram profile posts
APIFY_ACTOR = "apify/instagram-post-scraper"

EXTRACTION_PROMPT_TEMPLATE = (
    "You are an event extraction assistant. Given Instagram post captions from a Berlin venue, "
    "identify which posts announce specific upcoming events and extract structured data.\n\n"
    "For each post that IS an event announcement, return:\n"
    '{"title": "Event title or name", "start_time": "ISO 8601 datetime (YYYY-MM-DDTHH:MM:SS) '
    'in Berlin time, or YYYY-MM-DD if no time", "end_time": "ISO 8601 or null", '
    '"description": "Short description (max 300 chars) or null", '
    '"price": "e.g. \'€12\', \'Free\', \'€8-15\', or null", '
    '"image_url": "from post data, or null", "post_url": "Instagram post URL"}\n\n'
    "Rules:\n"
    "- Current date: TODAY_PLACEHOLDER\n"
    "- Current year: YEAR_PLACEHOLDER\n"
    "- ONLY extract posts that announce a specific event with a date. Skip:\n"
    "  - General atmosphere/vibe posts (\"great night last weekend\")\n"
    "  - Menu updates, hiring posts, holiday greetings\n"
    "  - Recurring schedule announcements without a specific date (\"every Thursday\")\n"
    "  - Past events (dates before today)\n"
    "- Parse German dates and times: \"Fr. 18. April\", \"18.04.\", \"Freitag 21h\", \"Doors 22:00\"\n"
    "- If a post says \"morgen\" or \"heute\", calculate from the post date, not today.\n"
    "- If year is missing, assume current year.\n"
    "- \"Eintritt frei\" / \"free entry\" -> price: \"Free\"\n"
    "- Return an empty array [] if NO posts contain event announcements.\n\n"
    "Return ONLY a JSON array. No explanation."
)


class InstagramEventsScraper(BaseScraper):
    source_name = "instagram"

    def __init__(self):
        super().__init__()
        self._venues = self._load_venues()
        self._apify: ApifyClient | None = None
        self._anthropic: anthropic.Anthropic | None = None

    def _load_venues(self) -> list[dict[str, Any]]:
        """Load venues that have Instagram as a source but no website or RA."""
        if not SOURCES_PATH.exists():
            logger.error("venue_sources.json not found at %s", SOURCES_PATH)
            return []

        with open(SOURCES_PATH) as f:
            all_venues = json.load(f)

        venues = []
        for name, config in all_venues.items():
            sources = config.get("sources", {})
            if "instagram" not in sources:
                continue
            # Skip venues already covered by website or RA scrapers
            if "website" in sources or "ra" in sources:
                continue
            venues.append({
                "name": name,
                "instagram": sources["instagram"],
                "lat": config.get("lat"),
                "lng": config.get("lng"),
                "address": config.get("address"),
                "neighborhood": config.get("neighborhood", "Neukölln"),
            })
        return venues

    def _get_apify(self) -> ApifyClient:
        if self._apify is None:
            token = os.environ.get("APIFY_TOKEN")
            if not token:
                raise RuntimeError("APIFY_TOKEN not set")
            self._apify = ApifyClient(token)
        return self._apify

    def _get_anthropic(self) -> anthropic.Anthropic:
        if self._anthropic is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError("ANTHROPIC_API_KEY not set")
            self._anthropic = anthropic.Anthropic(api_key=api_key)
        return self._anthropic

    def scrape(self) -> list[dict[str, Any]]:
        """Scrape all Instagram-only venues via Apify."""
        all_events: list[dict[str, Any]] = []

        # Batch all handles into one Apify run to save API calls
        handles = [v["instagram"] for v in self._venues]
        logger.info("Fetching posts for %d Instagram profiles via Apify...", len(handles))

        posts_by_handle = self._fetch_posts_batch(handles)

        for venue in self._venues:
            handle = venue["instagram"]
            posts = posts_by_handle.get(handle, [])
            if not posts:
                logger.info("@%s (%s): no posts found", handle, venue["name"])
                continue

            try:
                events = self._extract_events_for_venue(posts, venue)
                all_events.extend(events)
                logger.info("@%s (%s): %d events from %d posts", handle, venue["name"], len(events), len(posts))
            except Exception as e:
                logger.warning("LLM extraction failed for @%s: %s", handle, e)

        logger.info("instagram: %d total events from %d venues", len(all_events), len(self._venues))
        return all_events

    def _fetch_posts_batch(self, handles: list[str]) -> dict[str, list[dict]]:
        """Fetch recent posts for multiple IG profiles in one Apify run."""
        client = self._get_apify()
        cutoff = datetime.now() - timedelta(days=POST_AGE_LIMIT_DAYS)

        run_input = {
            "username": handles,
            "resultsLimit": MAX_POSTS_PER_VENUE,
        }

        logger.info("Starting Apify run for %d profiles...", len(handles))
        run = client.actor(APIFY_ACTOR).call(run_input=run_input)

        # Collect results grouped by owner
        posts_by_handle: dict[str, list[dict]] = {}
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            owner = (item.get("ownerUsername") or "").lower()
            if not owner:
                continue

            timestamp = item.get("timestamp")
            if timestamp:
                try:
                    post_date = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).replace(tzinfo=None)
                    if post_date < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass

            caption = item.get("caption") or ""
            if not caption.strip():
                continue

            post_data = {
                "caption": caption[:1000],
                "date": (timestamp or "")[:10],
                "image_url": item.get("displayUrl"),
                "post_url": item.get("url") or f"https://www.instagram.com/p/{item.get('shortCode', '')}/",
            }

            if owner not in posts_by_handle:
                posts_by_handle[owner] = []
            posts_by_handle[owner].append(post_data)

        logger.info("Apify returned posts for %d/%d profiles", len(posts_by_handle), len(handles))
        return posts_by_handle

    def _extract_events_for_venue(self, posts: list[dict], venue: dict) -> list[dict[str, Any]]:
        """Use Claude to extract events from post captions, then attach venue metadata."""
        raw_events = self._call_llm(posts, venue)

        events = []
        for raw in raw_events:
            title = raw.get("title", "").strip()
            if not title:
                continue
            events.append({
                "title": title,
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
                "source_url": raw.get("post_url") or f"https://www.instagram.com/{venue['instagram']}/",
                "source_id": f"ig_{venue['instagram']}_{raw.get('start_time', '')}_{title[:20]}",
                "source": self.source_name,
            })

        return events

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _call_llm(self, posts: list[dict], venue: dict) -> list[dict]:
        """Use Claude to identify event announcements from IG captions."""
        client = self._get_anthropic()
        today = datetime.now().strftime("%Y-%m-%d")
        year = str(datetime.now().year)

        posts_text = ""
        for p in posts:
            posts_text += f"\n--- Post from {p['date']} ---\n"
            posts_text += f"Caption: {p['caption']}\n"
            posts_text += f"Image: {p['image_url']}\n"
            posts_text += f"Link: {p['post_url']}\n"

        prompt = EXTRACTION_PROMPT_TEMPLATE.replace("TODAY_PLACEHOLDER", today).replace("YEAR_PLACEHOLDER", year)

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system=[{
                "type": "text",
                "text": prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": (
                    f"Venue: {venue['name']} (@{venue['instagram']})\n\n"
                    f"Recent Instagram posts:\n{posts_text}"
                ),
            }],
        )

        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        results = json.loads(raw)
        if not isinstance(results, list):
            results = [results] if results else []

        return results
