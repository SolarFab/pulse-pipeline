"""
Meetup.com scraper — uses their GraphQL API.
Auth: https://www.meetup.com/api/oauth/list/
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://api.meetup.com/gql"

# GraphQL query for upcoming events in Berlin
EVENTS_QUERY = """
query BerlinEvents($lat: Float!, $lon: Float!, $radius: Float!, $after: String) {
  eventsSearch(
    filter: {
      lat: $lat
      lon: $lon
      radius: $radius
      startDateRange: $after
      eventType: PHYSICAL
    }
    input: { first: 100 }
  ) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        title
        dateTime
        endTime
        description
        eventUrl
        isOnline
        images {
          baseUrl
        }
        venue {
          name
          address
          lat
          lng
          neighborhood
          city
        }
        group {
          name
          city
        }
        feeSettings {
          accepts
          amount
          currency
          type
        }
        topics {
          name
        }
      }
    }
  }
}
"""

BERLIN_LAT = 52.5200
BERLIN_LNG = 13.4050
RADIUS_KM = 25.0


class MeetupScraper(BaseScraper):
    source_name = "meetup"

    def scrape(self) -> list[dict[str, Any]]:
        api_key = os.environ.get("MEETUP_API_KEY")
        if not api_key:
            logger.warning("No MEETUP_API_KEY — skipping Meetup scraper")
            return []

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        events = []
        cursor = None
        now_iso = datetime.now(UTC).isoformat()

        while True:
            variables = {
                "lat": BERLIN_LAT,
                "lon": BERLIN_LNG,
                "radius": RADIUS_KM,
                "after": now_iso,
            }
            if cursor:
                variables["after"] = cursor  # reuse for pagination

            try:
                import httpx

                with httpx.Client(timeout=30) as client:
                    resp = client.post(
                        GRAPHQL_URL,
                        json={"query": EVENTS_QUERY, "variables": variables},
                        headers=headers,
                    )
                    resp.raise_for_status()
                    data = resp.json()
            except Exception as e:
                logger.error("Meetup GraphQL error: %s", e)
                break

            search = data.get("data", {}).get("eventsSearch", {})
            edges = search.get("edges", [])

            for edge in edges:
                node = edge.get("node", {})
                event = self._parse_event(node)
                if event:
                    events.append(event)

            page_info = search.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

        logger.info("meetup: fetched %d events", len(events))
        return events

    def _parse_event(self, node: dict) -> dict | None:
        try:
            title = node.get("title", "").strip()
            if not title or node.get("isOnline"):
                return None

            venue = node.get("venue") or {}
            group = node.get("group") or {}

            venue_name = venue.get("name") or group.get("name") or "Unknown"
            address = venue.get("address")
            if venue.get("city"):
                address = f"{address}, {venue['city']}" if address else venue["city"]

            lat = venue.get("lat")
            lng = venue.get("lng")

            # Skip if clearly outside Berlin
            if lat and (lat < 52.3 or lat > 52.7):
                return None
            if lng and (lng < 13.1 or lng > 13.8):
                return None

            description = node.get("description", "").strip() or None

            fee = node.get("feeSettings") or {}
            price = self._extract_price(fee)

            images = node.get("images") or []
            image_url = images[0].get("baseUrl") if images else None

            topics = [t.get("name", "") for t in (node.get("topics") or [])]
            source_tags = [t for t in topics if t]  # preserve original Meetup topics
            category = self._map_topics(topics)

            return {
                "title": title,
                "venue_name": venue_name,
                "address": address,
                "lat": float(lat) if lat else None,
                "lng": float(lng) if lng else None,
                "neighborhood": venue.get("neighborhood"),
                "start_time": node.get("dateTime"),
                "end_time": node.get("endTime"),
                "description": description,
                "price": price,
                "image_url": image_url,
                "source_url": node.get("eventUrl"),
                "source_id": node.get("id"),
                "category": category,
                "tags": [t.lower() for t in topics[:6]],
                "source_tags": source_tags,
                "source": self.source_name,
            }
        except Exception as e:
            logger.warning("Meetup parse error: %s", e)
            return None

    def _extract_price(self, fee: dict) -> str | None:
        if not fee:
            return "Free"
        amount = fee.get("amount")
        currency = fee.get("currency", "€")
        if not amount or float(amount) == 0:
            return "Free"
        return f"{currency}{amount}"

    def _map_topics(self, topics: list[str]) -> str | None:
        combined = " ".join(topics).lower()
        if any(w in combined for w in ("tech", "coding", "programming", "startup", "ai")):
            return "meetups"
        if any(w in combined for w in ("language", "deutsch", "english", "speaking")):
            return "meetups"
        if any(w in combined for w in ("hiking", "running", "cycling", "outdoor", "sport")):
            return "outdoors"
        if any(w in combined for w in ("yoga", "meditation", "wellness", "mindfulness")):
            return "outdoors"
        if any(w in combined for w in ("music", "concert", "jazz", "band")):
            return "music"
        if any(w in combined for w in ("food", "cooking", "dining", "wine", "beer")):
            return "food"
        if any(w in combined for w in ("art", "gallery", "photography", "painting")):
            return "culture"
        if any(w in combined for w in ("game", "board game", "tabletop", "rpg")):
            return "meetups"
        return "meetups"
