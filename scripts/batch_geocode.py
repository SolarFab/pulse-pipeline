"""
Batch geocoder for events without coordinates.

Two passes per venue:
1. Match against the venues table (2,500+ venues already have coords) —
   free, instant, and links events via venue_id so the events_with_coords
   view resolves them automatically.
2. Nominatim lookup (1 req/3s, respectful of their rate limit) for the rest;
   successful results are inserted into the venues table so future events at
   the same venue resolve without another lookup.

Only touches active future events — deactivated/past rows stay as-is.

Usage: python scripts/batch_geocode.py [--limit N]
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)-8s %(message)s", stream=sys.stderr)
logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "NachtKarte/1.0 (Berlin event discovery app)"}

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def geocode(query: str) -> tuple[float, float] | None:
    try:
        resp = httpx.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "de"},
            headers=HEADERS,
            timeout=10,
        )
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:
        logger.debug("Geocode failed for %r: %s", query, e)
    return None


def geocode_venue(venue: str, address: str | None) -> tuple[float, float] | None:
    result = None
    # Strategy 1: Full address
    if address and len(address) > 5:
        clean = address.replace(";", ",")
        result = geocode(clean)
        if not result:
            time.sleep(3)
            result = geocode(f"{clean}, Berlin, Germany")
    # Strategy 2: Venue name + Berlin
    if not result and venue and venue not in (".", "TBA", "Unknown"):
        time.sleep(3)
        result = geocode(f"{venue}, Berlin, Germany")
    return result


def fetch_events_missing_coords() -> list[dict]:
    """Active future events with neither coords nor a venue link."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    rows: list[dict] = []
    offset = 0
    while True:
        batch = (
            supabase.table("events")
            .select("id,venue_name,address")
            .is_("lat", "null")
            .is_("venue_id", "null")
            .eq("is_active", True)
            .gte("start_time", cutoff)
            .range(offset, offset + 999)
            .execute()
            .data
        )
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


def load_known_venues() -> dict[str, dict]:
    """All venues with coords, keyed by lowercased name."""
    venues: dict[str, dict] = {}
    offset = 0
    while True:
        batch = (
            supabase.table("venues")
            .select("id,name,lat,lng")
            .range(offset, offset + 999)
            .execute()
            .data
        )
        for v in batch:
            if v.get("lat") is not None:
                venues[v["name"].lower().strip()] = v
        if len(batch) < 1000:
            break
        offset += 1000
    return venues


def update_events(ids: list[str], patch: dict) -> None:
    for i in range(0, len(ids), 100):
        supabase.table("events").update(patch).in_("id", ids[i : i + 100]).execute()


def main(limit: int | None = None) -> None:
    events = fetch_events_missing_coords()
    logger.info("Active future events missing coordinates: %d", len(events))

    # Group by venue name
    by_venue: dict[str, dict] = {}
    for e in events:
        key = e["venue_name"].lower().strip()
        entry = by_venue.setdefault(key, {"name": e["venue_name"], "address": e.get("address"), "ids": []})
        entry["ids"].append(e["id"])
        if not entry["address"] and e.get("address"):
            entry["address"] = e["address"]

    logger.info("Unique venues: %d", len(by_venue))

    # Pass 1: venues table match (free)
    known = load_known_venues()
    matched = 0
    remaining: list[dict] = []
    for key, entry in by_venue.items():
        v = known.get(key)
        if v:
            update_events(entry["ids"], {"venue_id": v["id"], "lat": v["lat"], "lng": v["lng"]})
            matched += 1
        else:
            remaining.append(entry)
    logger.info("Pass 1 (venues table): matched %d venues; %d need Nominatim", matched, len(remaining))

    if limit is not None:
        remaining = remaining[:limit]

    # Pass 2: Nominatim
    geocoded = failed = 0
    for i, entry in enumerate(remaining):
        coords = geocode_venue(entry["name"], entry["address"])
        if coords:
            lat, lng = coords
            venue_id = None
            try:
                inserted = (
                    supabase.table("venues")
                    .insert({"name": entry["name"], "lat": lat, "lng": lng, "address": entry["address"]})
                    .execute()
                    .data
                )
                venue_id = inserted[0]["id"] if inserted else None
            except Exception:
                pass  # duplicate name+coords — coords on the events are enough
            patch = {"lat": lat, "lng": lng}
            if venue_id:
                patch["venue_id"] = venue_id
            update_events(entry["ids"], patch)
            geocoded += 1
            logger.info("[%d/%d] ✓ %s → (%.4f, %.4f) — %d events",
                        i + 1, len(remaining), entry["name"], lat, lng, len(entry["ids"]))
        else:
            failed += 1
            logger.info("[%d/%d] ✗ %s (no result)", i + 1, len(remaining), entry["name"])
        time.sleep(3)

    logger.info("Done. venues-table matches: %d, geocoded: %d, failed: %d", matched, geocoded, failed)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="max venues to send to Nominatim")
    main(limit=ap.parse_args().limit)
