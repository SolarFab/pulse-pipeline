#!/usr/bin/env python3
"""Backfill structured venue location fields from addresses and coordinates.

The script is a dry run unless ``--apply`` is passed. Reverse-geocoder responses
are cached after every request, so an interrupted run resumes without repeating
external calls. Nominatim's public-service limit is respected at one request per
second.

Examples:
    uv run python scripts/backfill_venue_locations.py --parse-only
    uv run python scripts/backfill_venue_locations.py --parse-only --apply
    uv run python scripts/backfill_venue_locations.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from pipeline.geocoder import HEADERS
from pipeline.venue_location import (
    fields_from_reverse_result,
    normalize_neighborhood,
    parse_address,
)
from supabase import create_client

load_dotenv()

REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
CACHE_PATH = Path(__file__).resolve().parents[1] / "eval" / "cache" / "venue_reverse.json"
PAGE_SIZE = 1000


def load_cache(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_cache(path: Path, cache: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True))


def coordinate_key(row: dict[str, Any]) -> str:
    return f"{float(row['lat']):.6f},{float(row['lng']):.6f}"


def fetch_venues(client: Any, limit: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    columns = "id,name,address,lat,lng,neighborhood,postal_code,city,district"
    while limit is None or len(rows) < limit:
        page_size = min(PAGE_SIZE, limit - len(rows)) if limit is not None else PAGE_SIZE
        end = offset + page_size - 1
        batch = client.table("venues").select(columns).range(offset, end).execute().data
        rows.extend(batch)
        if len(batch) < end - offset + 1:
            break
        offset += len(batch)
    return rows


def reverse_geocode(http: httpx.Client, row: dict[str, Any]) -> dict[str, Any]:
    response = http.get(
        REVERSE_URL,
        params={
            "lat": row["lat"],
            "lon": row["lng"],
            "format": "jsonv2",
            "addressdetails": 1,
            "zoom": 18,
        },
        headers=HEADERS,
        timeout=20,
    )
    response.raise_for_status()
    result = response.json()
    return result if isinstance(result, dict) else {}


def build_update(row: dict[str, Any], reverse: dict[str, Any] | None) -> dict[str, Any]:
    update = parse_address(row.get("address"))
    current_neighborhood = normalize_neighborhood(row.get("neighborhood"), city=row.get("city"))
    update["neighborhood"] = current_neighborhood

    if reverse:
        derived = fields_from_reverse_result(reverse)
        for field in ("postal_code", "city", "district"):
            if not update.get(field) and derived.get(field):
                update[field] = derived[field]
        if not current_neighborhood and derived.get("neighborhood"):
            update["neighborhood"] = derived["neighborhood"]

    return {key: value for key, value in update.items() if row.get(key) != value}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write planned updates to Supabase")
    parser.add_argument(
        "--parse-only", action="store_true", help="derive only from existing address text"
    )
    parser.add_argument("--limit", type=int, default=None, help="process at most this many venues")
    parser.add_argument("--delay", type=float, default=1.0, help="seconds between Nominatim calls")
    parser.add_argument("--cache", type=Path, default=CACHE_PATH)
    args = parser.parse_args()

    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    venues = fetch_venues(client, args.limit)
    cache = load_cache(args.cache)
    plans: list[tuple[str, dict[str, Any]]] = []
    failures: list[str] = []
    written = 0

    coordinates = {coordinate_key(row) for row in venues if row.get("lat") is not None}
    uncached = coordinates - set(cache)
    print(
        f"[plan] {len(venues)} venues; {len(coordinates)} distinct coordinates; "
        f"{len(uncached) if not args.parse_only else 0} reverse lookups needed"
    )

    with httpx.Client() as http:
        for index, row in enumerate(venues, 1):
            reverse = None
            if not args.parse_only and row.get("lat") is not None and row.get("lng") is not None:
                key = coordinate_key(row)
                if key not in cache:
                    try:
                        cache[key] = reverse_geocode(http, row)
                        save_cache(args.cache, cache)
                    except (httpx.HTTPError, ValueError) as exc:
                        failures.append(f"{row['id']}: {type(exc).__name__}")
                        continue
                    time.sleep(max(args.delay, 1.0))
                reverse = cache[key]

            update = build_update(row, reverse)
            if update:
                plans.append((row["id"], update))
                if args.apply:
                    client.table("venues").update(update).eq("id", row["id"]).execute()
                    written += 1
            if index % 100 == 0:
                suffix = f"; wrote {written}" if args.apply else ""
                print(f"  processed {index}/{len(venues)}{suffix}", flush=True)

    counts = Counter(key for _, update in plans for key in update)
    print(f"[plan] {len(plans)} venue rows change: {dict(sorted(counts.items()))}")
    if failures:
        print(f"[warning] {len(failures)} transient reverse-geocoding failures; not cached")

    if not args.apply:
        print("Dry run — nothing written. Re-run with --apply.")
        return 0

    print(f"[write] {written} venues updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
