"""Staging reader — the product side of the discovery-agent boundary (task 2.6).

The discovery agent is a separate repo that never touches this pipeline: it writes
rows into `discovered_events` and stops. This scraper picks them up and runs them
through the SAME normalize → categorize → facets → embed → upsert path as every
other source, so agent-found events are indistinguishable downstream.

Deliberately a BaseScraper subclass rather than a bespoke ingest script: the
contract between the two systems is a table, and everything after that table is
already solved here.
"""

from __future__ import annotations

import logging
from typing import Any

from db.supabase import get_client
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BATCH = 500


class DiscoveryStagingScraper(BaseScraper):
    source_name = "discovery_agent"

    def scrape(self) -> list[dict[str, Any]]:
        sb = get_client()
        rows = (
            sb.table("discovered_events")
            .select(
                "id,title,start_time,end_time,venue_name,address,url,"
                "description,price,publisher_id,publishers(name,website)"
            )
            .eq("ingested", False)
            .order("created_at")
            .limit(BATCH)
            .execute()
            .data
            or []
        )
        logger.info("discovery_staging: %d uningested row(s)", len(rows))

        events, ingested_ids = [], []
        for row in rows:
            publisher = row.get("publishers") or {}
            # The agent stages the venue name it read on the page; fall back to the
            # publisher's own name, which is the venue for kind='venue'.
            venue_name = row.get("venue_name") or publisher.get("name")
            if not (row.get("title") and row.get("start_time") and venue_name):
                # Never silently drop: mark it handled so it can't loop forever,
                # but say so — repeated warnings here mean a recipe is misparsing.
                logger.warning(
                    "discovery_staging: skipping incomplete row %s (%r)",
                    row["id"],
                    row.get("title"),
                )
                ingested_ids.append(row["id"])
                continue
            events.append(
                {
                    "title": row["title"],
                    "venue_name": venue_name,
                    "start_time": row["start_time"],
                    "end_time": row.get("end_time"),
                    "address": row.get("address"),
                    "description": row.get("description"),
                    "price": row.get("price"),
                    "source_url": row.get("url") or publisher.get("website"),
                    "source_id": row["id"],
                    "source": self.source_name,
                }
            )
            ingested_ids.append(row["id"])

        # "ingested" means HANDED OFF to the pipeline, not "became a row in events".
        # It cannot mean the latter: the event fingerprint is title+date with no
        # time, so several showtimes of one film on one day legitimately collapse
        # into a single event (371 staged rows -> 263 events in the first real run).
        # Marking only what landed would leave the collapsed rows queued forever,
        # re-processed every night. A re-run is idempotent via the fingerprint, so
        # the cost of marking early is at worst one lost batch on a hard crash.
        if ingested_ids and not self.dry_run:
            for event_id in ingested_ids:
                sb.table("discovered_events").update({"ingested": True}).eq(
                    "id", event_id
                ).execute()
            logger.info("discovery_staging: marked %d row(s) ingested", len(ingested_ids))

        return events
