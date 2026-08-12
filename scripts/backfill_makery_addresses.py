#!/usr/bin/env python3
"""Backfill the real workshop address for The Makery events.

The Makery is a MARKETPLACE, not a venue: every workshop runs at a partner
studio. The scraper geocoded the platform's own footer address
(John-Schehr-Strasse 2, 10407 Berlin), so every one of its events sits on one
point in Prenzlauer Berg while their neighborhoods span 46 districts — 287
upcoming, 1,199 rows in total. No other venue in the catalogue shows this pattern.

Each workshop detail page carries both addresses. This script reads the partner
studio's address off the page and writes `address`, `lat`, `lng`.

Three phases, each cached to disk so a crash resumes instead of refetching:
    1. fetch   — one page per distinct source_url, through the discovery agent's
                 guarded fetch (https-only, DNS-checked, robots.txt, 1s/domain)
    2. geocode — Nominatim, per DISTINCT address, reusing pipeline.geocoder
    3. write   — only with --apply

Deliberately NOT touched: `venue_name`. The studio name sits at an unreliable
position on the page (the line before the street is often a fragment — "5",
"Ateliers", "Then we walk to the park"). Street and postcode are reliable;
the name is not, and a half-right venue name is worse than a known-wrong one.

Usage:
    uv run python scripts/backfill_makery_addresses.py            # dry run
    uv run python scripts/backfill_makery_addresses.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from supabase import create_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, "/Users/solarlord/Projects/pulse/pulse-discovery-agent/src")

from discovery_agent.guards import FetchRefused, FetchSession  # noqa: E402

from pipeline.geocoder import geocode  # noqa: E402

load_dotenv()

CACHE = Path(__file__).resolve().parents[1] / "eval" / "cache"
PAGES = CACHE / "makery_pages.json"
GEO = CACHE / "makery_geocodes.json"

VENUE = "The Makery"
MAKERY_HQ_STREET = "John-Schehr-Strasse 2"  # the platform footer — never the venue
PLZ_LINE = re.compile(r"^(\d{5})\s+Berlin$")
# Berlin bounding box. A geocode outside it is a mismatch, not a location.
BBOX = (52.3, 52.7, 13.0, 13.8)


def _sb():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _load(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1))


def extract_address(html: str) -> dict | None:
    """The partner studio's address block: <name> / <street> / <plz> Berlin / <kiez>.

    Anchored on the "<5 digits> Berlin" line, which is unambiguous, and skipping
    the block whose street is the platform's own.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    lines = [line for line in soup.get_text("\n", strip=True).split("\n") if line]
    for i, line in enumerate(lines):
        m = PLZ_LINE.match(line)
        if not m or i < 2:
            continue
        street = lines[i - 1]
        if street == MAKERY_HQ_STREET:
            continue
        return {
            "street": street,
            "plz": m.group(1),
            "kiez_on_page": lines[i + 1] if i + 1 < len(lines) else None,
            "name_guess": lines[i - 2],  # recorded, never written — see docstring
        }
    return None


def phase_fetch(rows: list[dict]) -> dict:
    pages = _load(PAGES)
    todo = [r for r in rows if r["source_url"] not in pages]
    print(
        f"[fetch] {len(pages)} cached, {len(todo)} to fetch "
        f"(~{len(todo)}s at 1 req/s politeness)"
    )
    session = FetchSession()
    for n, row in enumerate(todo, 1):
        url = row["source_url"]
        try:
            found = extract_address(session.guarded_fetch(url).text)
            pages[url] = found or {"error": "no address block found"}
        except (FetchRefused, Exception) as exc:  # noqa: BLE001
            pages[url] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
        if n % 25 == 0:
            _save(PAGES, pages)
            print(f"  {n}/{len(todo)}", flush=True)
    _save(PAGES, pages)
    ok = sum(1 for v in pages.values() if "street" in v)
    print(f"[fetch] {ok}/{len(pages)} pages yielded an address")
    return pages


def phase_geocode(pages: dict) -> dict:
    geo = _load(GEO)
    wanted = {f"{v['street']}, {v['plz']} Berlin, Germany" for v in pages.values() if "street" in v}
    todo = sorted(wanted - set(geo))
    print(
        f"[geocode] {len(wanted)} distinct addresses, {len(todo)} new "
        f"(~{len(todo)}s at 1 req/s)"
    )
    for n, addr in enumerate(todo, 1):
        hit = geocode(addr)
        if hit and BBOX[0] <= hit[0] <= BBOX[1] and BBOX[2] <= hit[1] <= BBOX[3]:
            geo[addr] = {"lat": hit[0], "lng": hit[1]}
        else:
            # Out-of-Berlin or no hit: record the refusal so we never write it and
            # never retry it blindly.
            geo[addr] = {"error": f"no usable hit ({hit})"}
        time.sleep(1.0)  # Nominatim usage policy
        if n % 25 == 0:
            _save(GEO, geo)
            print(f"  {n}/{len(todo)}", flush=True)
    _save(GEO, geo)
    ok = sum(1 for v in geo.values() if "lat" in v)
    print(f"[geocode] {ok}/{len(geo)} addresses resolved")
    return geo


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write to the database")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    sb = _sb()
    rows, page = [], 0
    while True:
        batch = (
            sb.table("events")
            .select("id,title,neighborhood,source_url,lat")
            .eq("venue_name", VENUE)
            .eq("is_active", True)
            # An explicit instant, NOT the string "now()": PostgREST does not
            # evaluate that as a function, and it silently widened the set to
            # everything from today 00:00 — 722 rows instead of 287.
            .gte("start_time", datetime.now(UTC).isoformat())
            .range(page * 1000, page * 1000 + 999)
            .execute()
            .data
        )
        rows += batch
        if len(batch) < 1000:
            break
        page += 1
    if args.limit:
        rows = rows[: args.limit]
    print(
        f"[db] {len(rows)} future '{VENUE}' events, "
        f"{len({r['source_url'] for r in rows})} distinct pages"
    )

    pages = phase_fetch(rows)
    geo = phase_geocode(pages)

    updates, skipped = [], {"no_address": 0, "no_geocode": 0}
    for row in rows:
        found = pages.get(row["source_url"], {})
        if "street" not in found:
            skipped["no_address"] += 1
            continue
        key = f"{found['street']}, {found['plz']} Berlin, Germany"
        coords = geo.get(key, {})
        if "lat" not in coords:
            skipped["no_geocode"] += 1
            continue
        updates.append(
            {
                "id": row["id"],
                "address": f"{found['street']}, {found['plz']} Berlin",
                "lat": coords["lat"],
                "lng": coords["lng"],
            }
        )

    print(
        f"\n[plan] {len(updates)} events to update; "
        f"skipped: {skipped['no_address']} without address, "
        f"{skipped['no_geocode']} without geocode"
    )
    distinct = {(u["lat"], u["lng"]) for u in updates}
    print(f"[plan] they land on {len(distinct)} distinct coordinates " f"(was 1 for all of them)")
    for u in updates[:5]:
        print(f"   {u['address']:<44} {u['lat']:.5f}, {u['lng']:.5f}")

    if not args.apply:
        print("\nDry run — nothing written. Re-run with --apply.")
        return 0

    for n, u in enumerate(updates, 1):
        sb.table("events").update({"address": u["address"], "lat": u["lat"], "lng": u["lng"]}).eq(
            "id", u["id"]
        ).execute()
        if n % 100 == 0:
            print(f"  wrote {n}/{len(updates)}", flush=True)
    print(f"[write] {len(updates)} events updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
