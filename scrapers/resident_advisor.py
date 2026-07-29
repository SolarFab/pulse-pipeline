"""
Resident Advisor (ra.co) scraper.
Hits RA's public GraphQL API directly — no Playwright needed.
Covers Berlin club nights, techno, electronic music.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://ra.co/graphql"
BERLIN_AREA_ID = 34

EVENTS_QUERY = """
query GET_DEFAULT_EVENTS_LISTING($filters: FilterInputDtoInput, $pageSize: Int, $page: Int) {
  eventListings(filters: $filters, pageSize: $pageSize, page: $page) {
    data {
      event {
        id
        title
        content
        date
        startTime
        endTime
        contentUrl
        images {
          filename
        }
        venue {
          id
          name
          address
          area {
            name
          }
        }
        artists {
          name
        }
      }
    }
    totalResults
  }
}
"""


class ResidentAdvisorScraper(BaseScraper):
    source_name = "resident_advisor"

    def scrape(self) -> list[dict[str, Any]]:
        # 28-day window (RA_WINDOW_DAYS to override) — nightlife is the app's
        # core content and 14 days kept coverage far below other sources
        window_days = int(os.environ.get("RA_WINDOW_DAYS", "28"))
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        end_date = (datetime.now(UTC) + timedelta(days=window_days)).strftime("%Y-%m-%d")

        events = []
        page = 1
        max_pages = int(os.environ.get("RA_MAX_PAGES", "12"))

        while page <= max_pages:
            variables = {
                "filters": {
                    "areas": {"eq": BERLIN_AREA_ID},
                    "listingDate": {"gte": today, "lte": end_date},
                },
                "pageSize": 50,
                "page": page,
            }

            try:
                resp = self.post(
                    GRAPHQL_URL,
                    json={"query": EVENTS_QUERY, "variables": variables},
                    headers={
                        "Content-Type": "application/json",
                        "Referer": "https://ra.co/events/de/berlin",
                        "Origin": "https://ra.co",
                    },
                )
                body = resp.json()
            except Exception as e:
                logger.error("RA GraphQL request failed (page %d): %s", page, e)
                break

            listings = body.get("data", {}).get("eventListings", {}).get("data", [])
            if not listings:
                break

            for item in listings:
                event = item.get("event") or item
                parsed = self._parse_ra_event(event)
                if parsed:
                    events.append(parsed)

            total = body.get("data", {}).get("eventListings", {}).get("totalResults", 0)
            if page * 50 >= total:
                break
            page += 1

        # Deduplicate by source_id
        seen = set()
        unique = []
        for e in events:
            sid = e.get("source_id")
            if sid and sid not in seen:
                seen.add(sid)
                unique.append(e)

        logger.info("resident_advisor: scraped %d events", len(unique))
        return unique

    def _parse_ra_event(self, event: dict) -> dict | None:
        try:
            title = event.get("title", "").strip()
            if not title:
                return None

            venue = event.get("venue") or {}
            venue_name = venue.get("name", "").strip() or "Unknown"

            area = venue.get("area") or {}
            neighborhood = area.get("name")

            address = venue.get("address", "").strip() or None

            start_time = event.get("startTime") or event.get("date")
            end_time = event.get("endTime")

            # Image
            images = event.get("images") or []
            image_url = images[0].get("filename") if images else None
            if image_url and not image_url.startswith("http"):
                image_url = f"https://images.ra.co/{image_url}"

            # RA event ID → URL
            ra_id = event.get("id")
            content_url = event.get("contentUrl")
            source_url = (
                f"https://ra.co{content_url}"
                if content_url
                else (f"https://ra.co/events/{ra_id}" if ra_id else None)
            )

            # Description from RA content + artist lineup
            content = (event.get("content") or "").strip()
            artists = event.get("artists") or []
            artist_names = [a.get("name", "") for a in artists if a.get("name")]
            lineup = f"Lineup: {', '.join(artist_names[:10])}" if artist_names else ""
            if content and lineup:
                description = f"{content[:500]}\n\n{lineup}"
            elif content:
                description = content[:500]
            elif lineup:
                description = lineup
            else:
                description = None

            return {
                "title": title,
                "venue_name": venue_name,
                "address": address,
                "neighborhood": neighborhood,
                "start_time": start_time,
                "end_time": end_time,
                "description": description,
                "image_url": image_url,
                "source_url": source_url,
                "source_id": str(ra_id) if ra_id else None,
                "category": "nightlife",
                "tags": ["electronic", "club"],
                "source_tags": [],
                "source": self.source_name,
            }
        except Exception as e:
            logger.debug("RA event parse error: %s", e)
            return None
