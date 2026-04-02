"""
BaseScraper: shared HTTP client, normalization, and upsert logic.
All scrapers inherit from this.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from db.supabase import get_client, upsert_events
from pipeline.categorizer import categorize_batch
from pipeline.geocoder import geocode_inline
from pipeline.normalizer import normalize

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class BaseScraper(ABC):
    """
    Abstract base for all NachtKarte scrapers.

    Subclasses implement `scrape()` which returns a list of raw event dicts.
    The base class handles normalization, categorization, and DB upsert.
    """

    source_name: str  # must set in subclass, e.g. "kulturdaten"
    dry_run: bool = False

    def __init__(self):
        self.dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"
        self.logger = logging.getLogger(f"scraper.{self.source_name}")

    @abstractmethod
    def scrape(self) -> list[dict[str, Any]]:
        """
        Fetch and return raw event dicts from the source.
        Each dict should match the RawEvent model fields as closely as possible.
        """
        ...

    def run(self) -> tuple[int, int]:
        """
        Full pipeline: scrape → normalize → categorize → upsert.
        Returns (success_count, fail_count).
        """
        self.logger.info("Starting scrape: %s", self.source_name)

        try:
            raw_events = self.scrape()
        except Exception as e:
            self.logger.error("Scrape failed for %s: %s", self.source_name, e)
            return 0, 0

        self.logger.info("Scraped %d raw events from %s", len(raw_events), self.source_name)

        # Normalize
        normalised = []
        for raw in raw_events:
            raw.setdefault("source", self.source_name)
            result = normalize(raw)
            if result:
                normalised.append(result)

        self.logger.info("Normalised: %d / %d", len(normalised), len(raw_events))

        # Filter out events already in DB with complete categorization
        fingerprints = [e["fingerprint"] for e in normalised if e.get("fingerprint")]
        existing_fps: set[str] = set()
        if fingerprints:
            client = get_client()
            # Check in batches (Supabase .in_() has limits)
            for i in range(0, len(fingerprints), 500):
                batch_fps = fingerprints[i : i + 500]
                result = client.table("events").select("fingerprint").in_(
                    "fingerprint", batch_fps
                ).not_.is_("category", "null").not_.is_("tags", "null").execute()
                for row in result.data or []:
                    existing_fps.add(row["fingerprint"])

        new_events = [e for e in normalised if e.get("fingerprint") not in existing_fps]
        existing_events = [e for e in normalised if e.get("fingerprint") in existing_fps]
        self.logger.info("New: %d, already categorized in DB: %d (skipping LLM)", len(new_events), len(existing_events))

        # Geocode (fills in missing lat/lng)
        geocode_inline(new_events)

        # Categorize only new events (Claude fills in missing category/tags)
        categorised = categorize_batch(new_events) + existing_events

        # Upsert
        success, fail = upsert_events(categorised, dry_run=self.dry_run)
        self.logger.info("Upserted %d, failed %d", success, fail)
        return success, fail

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def get(self, url: str, **kwargs) -> httpx.Response:
        """GET with retries and default headers."""
        headers = {**DEFAULT_HEADERS, **kwargs.pop("headers", {})}
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(url, headers=headers, **kwargs)
            response.raise_for_status()
            return response

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def post(self, url: str, **kwargs) -> httpx.Response:
        """POST with retries and default headers."""
        headers = {**DEFAULT_HEADERS, **kwargs.pop("headers", {})}
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.post(url, headers=headers, **kwargs)
            response.raise_for_status()
            return response

    def get_json(self, url: str, **kwargs) -> Any:
        resp = self.get(url, **kwargs)
        return resp.json()
