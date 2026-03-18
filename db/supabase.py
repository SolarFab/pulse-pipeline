"""Supabase client and upsert logic for the NachtKarte pipeline."""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()
logger = logging.getLogger(__name__)

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_KEY"]
        _client = create_client(url, key)
    return _client


def upsert_event(event: dict[str, Any], dry_run: bool = False) -> bool:
    """
    Upsert a single event by fingerprint. Returns True if inserted/updated.
    The fingerprint column has a UNIQUE constraint — conflicts update in place.
    """
    if not event.get("fingerprint"):
        logger.warning("Skipping event with no fingerprint: %s", event.get("title"))
        return False

    if dry_run:
        logger.info("[DRY RUN] Would upsert: %s @ %s", event.get("title"), event.get("venue_name"))
        return True

    try:
        client = get_client()
        client.table("events").upsert(
            event,
            on_conflict="fingerprint",
            ignore_duplicates=False,  # always update existing rows
        ).execute()
        return True
    except Exception as e:
        logger.error("Failed to upsert event '%s': %s", event.get("title"), e)
        return False


def upsert_events(events: list[dict[str, Any]], dry_run: bool = False) -> tuple[int, int]:
    """Bulk upsert. Returns (success_count, fail_count)."""
    if not events:
        return 0, 0

    if dry_run:
        logger.info("[DRY RUN] Would upsert %d events", len(events))
        return len(events), 0

    # Filter out events without fingerprints
    valid = [e for e in events if e.get("fingerprint")]
    invalid_count = len(events) - len(valid)
    if invalid_count:
        logger.warning("Skipping %d events without fingerprints", invalid_count)

    # Deduplicate by fingerprint (keep last occurrence) to avoid batch upsert conflict
    seen: dict[str, dict] = {}
    for e in valid:
        seen[e["fingerprint"]] = e
    if len(seen) < len(valid):
        logger.info("Deduplicated %d → %d events by fingerprint", len(valid), len(seen))
    valid = list(seen.values())

    # Batch upsert in chunks to avoid Supabase statement timeout
    BATCH_SIZE = 500
    client = get_client()
    success, fail = 0, 0

    for i in range(0, len(valid), BATCH_SIZE):
        batch = valid[i : i + BATCH_SIZE]
        try:
            client.table("events").upsert(
                batch,
                on_conflict="fingerprint",
                ignore_duplicates=False,
            ).execute()
            success += len(batch)
            if (i + BATCH_SIZE) % 2000 == 0 or i + BATCH_SIZE >= len(valid):
                logger.info("Upserted %d / %d events", min(i + BATCH_SIZE, len(valid)), len(valid))
        except Exception as e:
            logger.error("Batch upsert failed at offset %d: %s", i, e)
            # Fall back to one-by-one for this batch
            for event in batch:
                if upsert_event(event, dry_run):
                    success += 1
                else:
                    fail += 1

    return success, fail + invalid_count


def get_pending_events() -> list[dict]:
    """Fetch community-submitted events awaiting review."""
    client = get_client()
    result = client.table("events").select("*").eq("status", "pending").execute()
    return result.data or []


def approve_event(event_id: str) -> bool:
    """Approve a pending community submission."""
    try:
        client = get_client()
        client.table("events").update({"status": "active"}).eq("id", event_id).execute()
        return True
    except Exception as e:
        logger.error("Failed to approve event %s: %s", event_id, e)
        return False
