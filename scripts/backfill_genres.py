#!/usr/bin/env python3
"""Backfill genre tags over stored events (genre-dimension §2.6).

Runs the same deterministic waterfall as the scrape pass — alias-mapped
source_tags, then conservative text detection — over rows already in the DB, so
the genre dimension is populated without re-scraping and without an LLM.

Scope: active events from now on (past events never rank). Idempotent.

Usage:
    python scripts/backfill_genres.py --dry-run   # counts + coverage, no writes
    python scripts/backfill_genres.py             # write
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

from db.supabase import get_client  # noqa: E402
from pipeline.genres import GENRE_SLUGS, merge_genres  # noqa: E402

PAGE = 500


def fetch_all(client, now_iso: str) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        page = (
            client.table("events")
            .select("id,title,description,genres,source_tags,category,source")
            .eq("is_active", True)
            .gte("start_time", now_iso)
            .order("start_time")
            .range(offset, offset + PAGE - 1)
            .execute()
            .data
            or []
        )
        rows.extend(page)
        if len(page) < PAGE:
            return rows
        offset += PAGE


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    client = get_client()
    now_iso = datetime.now(UTC).isoformat()
    rows = fetch_all(client, now_iso)
    print(f"{len(rows)} active upcoming events")

    updates: list[tuple[str, list[str]]] = []
    added = Counter()
    for row in rows:
        before = list(row.get("genres") or [])
        after = merge_genres(row)
        if after != before:
            updates.append((row["id"], after))
            for slug in set(after) - set(before):
                added[slug] += 1

    with_genre = sum(1 for r in rows if set(merge_genres(r)) & GENRE_SLUGS)
    music_nightlife = [r for r in rows if r.get("category") in ("music", "nightlife")]
    mn_with_genre = sum(1 for r in music_nightlife if set(merge_genres(r)) & GENRE_SLUGS)

    print(f"{len(updates)} events gain genre tags")
    print(
        f"coverage after: {with_genre}/{len(rows)} all "
        f"({with_genre / max(len(rows), 1):.0%}) · "
        f"{mn_with_genre}/{len(music_nightlife)} music+nightlife "
        f"({mn_with_genre / max(len(music_nightlife), 1):.0%})"
    )
    print("top genres added: " + ", ".join(f"{g}={n}" for g, n in added.most_common(15)))

    if args.dry_run:
        return

    done = 0
    for event_id, genres in updates:
        try:
            client.table("events").update({"genres": genres}).eq("id", event_id).execute()
            done += 1
        except Exception as exc:
            print(f"  ! update failed for {event_id}: {type(exc).__name__}")
        if done % 250 == 0 and done:
            print(f"  {done}/{len(updates)}", flush=True)
    print(f"Done: {done} events updated")


if __name__ == "__main__":
    main()
