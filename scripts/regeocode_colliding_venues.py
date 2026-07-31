#!/usr/bin/env python3
"""Separate venues that share the exact same map point (the RAW-Gelände collision).

Distinct venues coarse-geocoded onto one coordinate make multi-venue pin clusters
(and mislabeled sheets). Fix: re-geocode each colliding venue by NAME via Nominatim
POI search, which resolves e.g. 'Crack Bellmer, Berlin' to its building.

Safety rails per venue:
  - new point must be < 500 m from the old one (same area — a name match landing
    across town is a different place with the same name; skip)
  - new point must be > 15 m from the old one (otherwise nothing gained)
Usage:  --dry-run first (prints the plan), then without to apply.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

from postgrest.exceptions import APIError  # noqa: E402

from db.supabase import get_client  # noqa: E402

UA = {"User-Agent": "PulseBerlin/1.0 (event map; venue geocoding)"}


def haversine_m(lat1, lng1, lat2, lng2) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def colliding_venues(client) -> list[dict]:
    """Venues used by upcoming events that share a rounded point with a DIFFERENT name."""
    rows = (
        client.table("venues").select("id,name,lat,lng").not_.is_("lat", "null").execute().data
    ) or []
    by_point: dict[tuple, list[dict]] = {}
    for v in rows:
        key = (round(float(v["lat"]), 5), round(float(v["lng"]), 5))
        by_point.setdefault(key, []).append(v)
    out = []
    for group in by_point.values():
        names = {v["name"].lower().strip() for v in group}
        if len(names) > 1:
            out.extend(group)
    return out


def nominatim_poi(name: str) -> tuple[float, float] | None:
    try:
        r = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{name}, Berlin", "format": "jsonv2", "limit": 1},
            headers=UA, timeout=20,
        )
        r.raise_for_status()
        hits = r.json()
        if hits:
            return float(hits[0]["lat"]), float(hits[0]["lon"])
    except httpx.HTTPError:
        pass
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    client = get_client()
    venues = colliding_venues(client)
    print(f"{len(venues)} venues sit on shared points with different names")

    moved = skipped_far = skipped_same = missed = 0
    for v in venues:
        time.sleep(1.1)  # Nominatim rate limit
        hit = nominatim_poi(v["name"])
        if not hit:
            missed += 1
            continue
        dist = haversine_m(float(v["lat"]), float(v["lng"]), hit[0], hit[1])
        if dist > 500:
            skipped_far += 1
            continue
        if dist < 15:
            skipped_same += 1
            continue
        print(f"  {v['name'][:45]:45} moves {dist:5.0f}m -> {hit[0]:.5f},{hit[1]:.5f}")
        if not args.dry_run:
            try:
                client.table("venues").update({"lat": hit[0], "lng": hit[1]}).eq("id", v["id"]).execute()
            except APIError as exc:
                if exc.code != "23505":
                    raise
                # A precise duplicate row (same name at the target point) already
                # exists — MERGE: relink this row's events to the precise twin.
                twin = (client.table("venues").select("id")
                        .eq("name", v["name"]).eq("lat", hit[0]).eq("lng", hit[1])
                        .limit(1).execute().data)
                if twin:
                    client.table("events").update({"venue_id": twin[0]["id"]}) \
                        .eq("venue_id", v["id"]).execute()
                    print(f"    ^ merged into precise duplicate row {twin[0]['id'][:8]}")
        moved += 1

    print(f"\n{'DRY RUN — ' if args.dry_run else ''}moved {moved}, "
          f"kept (already precise) {skipped_same}, "
          f"skipped (>500m sanity) {skipped_far}, no POI hit {missed}")


if __name__ == "__main__":
    main()
