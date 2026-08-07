#!/usr/bin/env python3
"""Seed the genre dimension into the canonical `taxonomy` table (genre-dimension §1.2).

Idempotent upsert on (kind, category_slug, subcategory_slug). Genre rows carry
`parent` (umbrella group) and `aliases` (source vocabularies -> canonical slug),
so the pipeline and the web app both read one vocabulary from the DB.

Usage:
    python scripts/seed_genres.py --dry-run   # print the plan
    python scripts/seed_genres.py             # write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

from db.supabase import get_client  # noqa: E402
from pipeline.genres import GENRE_GROUPS, genre_rows  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = genre_rows()
    genres = [r for r in rows if r["kind"] == "genre"]
    print(f"{len(GENRE_GROUPS)} groups + {len(genres)} genres")

    if args.dry_run:
        for group in GENRE_GROUPS:
            members = [r["category_slug"] for r in genres if r["parent"] == group]
            print(f"  {group:14} {', '.join(members)}")
        return

    client = get_client()
    client.table("taxonomy").upsert(
        rows, on_conflict="kind,category_slug,subcategory_slug"
    ).execute()
    print("Seeded.")


if __name__ == "__main__":
    main()
