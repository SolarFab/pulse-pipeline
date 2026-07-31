"""
Backfill missing subcategories on active future events using the same
Claude Haiku categorizer the pipeline uses (canonical taxonomy enforced).

Only writes category/subcategory (and quality_score when previously null) —
tags are left untouched to keep the blast radius small.

Usage:
    python scripts/backfill_subcategories.py --limit 50   # trial run
    python scripts/backfill_subcategories.py              # full run
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

import os  # noqa: E402

import anthropic  # noqa: E402
from supabase import create_client  # noqa: E402

from pipeline.categorizer import (  # noqa: E402
    CATEGORIES,
    _categorize_batch_call,
    normalize_subcategory,
)

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)-8s %(message)s", stream=sys.stderr)
logger = logging.getLogger("backfill_subcategories")

BATCH_SIZE = 20

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def fetch_targets() -> list[dict]:
    """Active future events with no subcategory."""
    now = datetime.now(UTC).isoformat()
    rows: list[dict] = []
    offset = 0
    while True:
        batch = (
            supabase.table("events")
            .select("id,title,venue_name,description,price,source,category,tags,subcategory,quality_score")
            .is_("subcategory", "null")
            .eq("is_active", True)
            .eq("status", "active")
            .gte("start_time", now)
            .order("start_time")
            .range(offset, offset + 999)
            .execute()
            .data
        )
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


def main(limit: int | None = None) -> None:
    events = fetch_targets()
    logger.info("Events missing subcategory: %d", len(events))
    if limit is not None:
        events = events[:limit]
        logger.info("Limiting to %d", limit)

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    updated = skipped = failed = 0
    for i in range(0, len(events), BATCH_SIZE):
        batch = events[i : i + BATCH_SIZE]
        try:
            results = _categorize_batch_call(client, batch)
        except Exception as e:
            logger.error("batch %d failed: %s", i // BATCH_SIZE, e)
            failed += len(batch)
            continue

        for event, result in zip(batch, results):
            category = result.get("category")
            if category not in CATEGORIES:
                skipped += 1
                continue
            sub = normalize_subcategory(category, result.get("subcategory"))
            if not sub:
                skipped += 1
                continue
            patch: dict = {"category": category, "subcategory": sub}
            if event.get("quality_score") is None and result.get("quality_score") is not None:
                patch["quality_score"] = result["quality_score"]
            try:
                supabase.table("events").update(patch).eq("id", event["id"]).execute()
                updated += 1
            except Exception as e:
                logger.warning("update failed for %s: %s", event["id"], e)
                failed += 1

        done = min(i + BATCH_SIZE, len(events))
        if done % 200 < BATCH_SIZE or done == len(events):
            logger.info("progress: %d/%d (updated %d, skipped %d, failed %d)",
                        done, len(events), updated, skipped, failed)

    logger.info("Done. updated=%d skipped=%d failed=%d", updated, skipped, failed)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    main(limit=ap.parse_args().limit)
