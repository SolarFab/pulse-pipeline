#!/usr/bin/env python3
"""Infer the last missing venue postcodes from coordinates (FEAT-22 tail).

The backfill derives a postcode from the venue's address. 68 venues have no
postcode in their address at all — "Wollankstr. 6, Berlin", "Potsdamer Platz,
Berlin" — but every one of them has accurate coordinates, and they host upcoming
events, so they are invisible to a postcode-based area search.

Rather than call a geocoder, this infers from the venues that ALREADY have a
postcode: take the nearest neighbours and adopt their postcode when they agree.
In a city this dense that is reliable, it costs nothing, and it cannot invent a
postcode that does not exist in Berlin.

The guard matters more than the inference. A postcode decides which Kiez an event
appears in, so a wrong one is worse than a missing one: missing degrades to a
wider search, wrong sends someone across town. So a value is written only when
the neighbours agree strongly and are genuinely close.

    uv run python scripts/infer_missing_postcodes.py            # dry run
    uv run python scripts/infer_missing_postcodes.py --write
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from collections import Counter
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv()

# A postcode is adopted only if enough of the nearest neighbours are BOTH close and
# in agreement. Berlin postcode areas are small; a neighbour 1.5 km away is
# routinely in a different one, so distance is the binding constraint.
#
# MIN_SUPPORT is the one that was missing. Agreement alone divided by however many
# happened to be close, so a single close neighbour scored 100% and its postcode
# was written on the strength of one data point. The share now has to clear the
# threshold AND rest on at least this many venues.
NEIGHBOURS = 7
MIN_AGREEMENT = 0.7
MIN_SUPPORT = 5
MAX_NEIGHBOUR_KM = 1.2


def haversine_km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def infer(lat: float, lng: float, known: list[dict]) -> tuple[str | None, float, float]:
    """Best postcode for a point, its agreement share, and the nearest distance.

    Returns (None, ...) when the neighbours disagree or are all too far — the
    honest outcome, because a wrong Kiez is worse than an unknown one.
    """
    ranked = sorted(
        ((haversine_km(lat, lng, k["lat"], k["lng"]), k["postal_code"]) for k in known),
        key=lambda x: x[0],
    )
    near = [(d, p) for d, p in ranked[:NEIGHBOURS] if d <= MAX_NEIGHBOUR_KM]
    if not near:
        return None, 0.0, ranked[0][0] if ranked else float("inf")

    counts = Counter(p for _, p in near)
    best, n = counts.most_common(1)[0]
    # Denominator is the full neighbour set, not just the close ones: otherwise a
    # lone close neighbour is 1/1 = 100% and decides the Kiez by itself.
    agreement = n / NEIGHBOURS
    if n < MIN_SUPPORT or agreement < MIN_AGREEMENT:
        return None, agreement, near[0][0]
    return best, agreement, near[0][0]


def fetch(url: str, key: str, params: dict) -> list[dict]:
    r = httpx.get(
        f"{url}/rest/v1/venues",
        params=params,
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="apply; otherwise dry run")
    args = ap.parse_args()

    url, key = os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
    known = fetch(
        url,
        key,
        {
            "select": "lat,lng,postal_code",
            "postal_code": "not.is.null",
            "lat": "not.is.null",
            "limit": "10000",
        },
    )
    missing = fetch(
        url,
        key,
        {
            "select": "id,name,lat,lng",
            "postal_code": "is.null",
            "lat": "not.is.null",
        },
    )
    print(f"{len(missing)} venues without a postcode · {len(known)} with one to learn from\n")

    resolved, skipped = [], []
    for v in missing:
        plz, agreement, nearest = infer(float(v["lat"]), float(v["lng"]), known)
        if plz:
            resolved.append(
                {
                    "id": v["id"],
                    "postal_code": plz,
                    "postal_code_source": "inferred_from_neighbours",
                    "postal_code_confidence": round(agreement, 2),
                }
            )
            print(
                f"  {v['name'][:44]:<44} -> {plz}  ({agreement:.0%} of neighbours, nearest {nearest:.2f} km)"
            )
        else:
            skipped.append(v)
            print(
                f"  {v['name'][:44]:<44} -- no confident answer ({agreement:.0%}, nearest {nearest:.2f} km)"
            )

    print(f"\n{len(resolved)} inferred, {len(skipped)} left alone")
    if not args.write:
        print("dry run — pass --write to apply")
        return

    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    for row in resolved:
        # Never overwrite: the filter re-checks that the column is still null, so a
        # concurrent backfill's real value always wins over this inference.
        httpx.patch(
            f"{url}/rest/v1/venues?id=eq.{row['id']}&postal_code=is.null",
            headers=h,
            json={"postal_code": row["postal_code"]},
            timeout=30,
        ).raise_for_status()
    print(f"wrote {len(resolved)} postcodes")


if __name__ == "__main__":
    main()
