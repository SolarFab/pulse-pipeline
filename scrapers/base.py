"""
BaseScraper: shared HTTP client, normalization, and upsert logic.
All scrapers inherit from this.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from db.supabase import get_client, get_venues_by_names, upsert_events
from pipeline.categorizer import categorize_batch
from pipeline.embed_events import attach_embeddings
from pipeline.facets import detect_facets
from pipeline.genres import merge_genres
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


@dataclass
class ScrapeOutcome:
    """What one source did, with failure distinguishable from emptiness.

    `error` is None when the source ran to completion, whatever it found. A
    source that legitimately has nothing on tonight is `upserted=0, error=None`;
    a source that blew up is `upserted=0, error="..."`. Conflating the two is
    the bug this type exists to prevent.
    """

    source: str
    upserted: int = 0
    rows_failed: int = 0  # individual events rejected during upsert
    error: str | None = None  # set only when the source itself failed

    @property
    def crashed(self) -> bool:
        return self.error is not None


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

    def run(self) -> ScrapeOutcome:
        """Full pipeline: scrape → normalize → categorize → upsert.

        Returns an outcome rather than a bare (success, fail) tuple, because the
        tuple could not tell "this source found nothing tonight" apart from "this
        source crashed" — both were (0, 0). That ambiguity is why `venue_website`
        and `instagram` produced zero rows for months while every run reported
        success. A caller must be able to count failures, so `error` carries them.
        """
        self.logger.info("Starting scrape: %s", self.source_name)

        try:
            raw_events = self.scrape()
        except Exception as e:
            self.logger.error("Scrape failed for %s: %s", self.source_name, e)
            return ScrapeOutcome(self.source_name, error=f"{type(e).__name__}: {e}")

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
                result = (
                    client.table("events")
                    .select("fingerprint")
                    .in_("fingerprint", batch_fps)
                    .not_.is_("category", "null")
                    .not_.is_("tags", "null")
                    .execute()
                )
                for row in result.data or []:
                    existing_fps.add(row["fingerprint"])

        new_events = [e for e in normalised if e.get("fingerprint") not in existing_fps]
        existing_events = [e for e in normalised if e.get("fingerprint") in existing_fps]
        self.logger.info(
            "New: %d, already categorized in DB: %d (skipping LLM)",
            len(new_events),
            len(existing_events),
        )

        # Geocode (fills in missing lat/lng)
        geocode_inline(new_events)

        # Categorize only new events (Claude fills in missing category/tags)
        categorised = categorize_batch(new_events) + existing_events

        # Facets + genres for ALL events (cheap regex, idempotent — also heals
        # rows that predate the columns). Genre order: source-native tags the
        # scraper already set win, then alias-mapped source_tags, then text
        # detection; nothing is ever removed, so a promoter's own genre always
        # outranks our guess.
        for event in categorised:
            event.update(detect_facets(event))
            event["genres"] = merge_genres(event)

        # Link events to venue rows by normalized name: the map resolves
        # coordinates through this join, so an unlinked event without its own
        # coords is invisible (the Berghain bug — 448/545 RA events off-map).
        unlinked = {
            e["venue_name"] for e in categorised if not e.get("venue_id") and e.get("venue_name")
        }
        if unlinked:
            vmap = get_venues_by_names(list(unlinked))
            linked = 0
            for event in categorised:
                if event.get("venue_id"):
                    continue
                v = vmap.get((event.get("venue_name") or "").lower().strip())
                if v:
                    event["venue_id"] = v["id"]
                    linked += 1
            self.logger.info(
                "Venue linking: %d events matched to venue rows (%d names unresolved)",
                linked,
                len(unlinked) - len(vmap),
            )

        # Embeddings: only new/changed embed text (hash-skip against stored hashes).
        # Failure degrades — events upsert without embeddings and heal next run.
        db_hashes: dict[str, str] = {}
        fps = [e["fingerprint"] for e in categorised if e.get("fingerprint")]
        if fps:
            for i in range(0, len(fps), 200):
                res = (
                    get_client()
                    .table("events")
                    .select("fingerprint,embed_hash")
                    .in_("fingerprint", fps[i : i + 200])
                    .execute()
                )
                db_hashes.update(
                    {
                        r["fingerprint"]: r["embed_hash"]
                        for r in (res.data or [])
                        if r.get("embed_hash")
                    }
                )
        emb_metrics = attach_embeddings(categorised, db_hashes)
        self.logger.info(
            "Embeddings: %(embedded)d new, %(skipped)d unchanged, "
            "%(failed)d failed — %(tokens)d tok / $%(usd).4f / %(seconds).1fs",
            emb_metrics,
        )

        # Upsert
        success, fail = upsert_events(categorised, dry_run=self.dry_run)
        self.logger.info("Upserted %d, failed %d", success, fail)
        return ScrapeOutcome(self.source_name, upserted=success, rows_failed=fail)

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
