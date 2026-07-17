"""
One-off / nightly DB maintenance:

1. Normalize legacy category values (market -> markets, social -> meetups, ...)
2. Normalize subcategories to the canonical taxonomy (synonyms remapped,
   unfixable values set to NULL so the LLM backfill can re-derive them)
3. Soft-delete past events (is_active = false once they ended > 30 days ago)

Usage:
    python scripts/db_cleanup.py --dry-run   # report only
    python scripts/db_cleanup.py             # apply

Uses the Supabase REST API with the service key from .env.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.categorizer import normalize_subcategory  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("db_cleanup")

CATEGORY_FIXES = {
    "market": "markets",
    "social": "meetups",
    "entertainment": "culture",
    "wellness": "outdoors",
}

PAST_EVENT_GRACE_DAYS = 30


def _load_env() -> tuple[str, str]:
    # Prefer process env; fall back to .env in the repo root
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
    return url, key


def _request(url: str, key: str, path: str, method: str = "GET", body: dict | None = None,
             prefer: str | None = None) -> tuple[object, dict]:
    req = urllib.request.Request(
        url + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            **({"Prefer": prefer} if prefer else {}),
        },
    )
    with urllib.request.urlopen(req) as resp:
        raw = resp.read()
        headers = dict(resp.headers)
        return (json.loads(raw) if raw else None), headers


def _count(url: str, key: str, filters: str) -> int:
    _, headers = _request(url, key, f"/rest/v1/events?select=id&{filters}&limit=1",
                          prefer="count=exact")
    return int(headers.get("Content-Range", "*/0").split("/")[-1])


def fix_categories(url: str, key: str, dry_run: bool) -> None:
    for old, new in CATEGORY_FIXES.items():
        n = _count(url, key, f"category=eq.{old}")
        if n == 0:
            continue
        logger.info("category %r -> %r: %d events%s", old, new, n, " (dry run)" if dry_run else "")
        if not dry_run:
            _request(url, key, f"/rest/v1/events?category=eq.{old}", "PATCH",
                     {"category": new}, prefer="return=minimal")


def fix_subcategories(url: str, key: str, dry_run: bool) -> None:
    # Pull every event that has a subcategory; normalize locally; patch diffs
    rows: list[dict] = []
    offset = 0
    while True:
        batch, _ = _request(
            url, key,
            f"/rest/v1/events?select=id,category,subcategory&subcategory=not.is.null&limit=1000&offset={offset}",
        )
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    changes: dict[tuple[str | None], list[str]] = {}
    stats = Counter()
    for r in rows:
        target = normalize_subcategory(r["category"], r["subcategory"])
        if target == r["subcategory"]:
            stats["ok"] += 1
            continue
        stats["remapped" if target else "nulled"] += 1
        changes.setdefault((target,), []).append(r["id"])

    logger.info("subcategories: %d ok, %d remapped, %d set to NULL%s",
                stats["ok"], stats["remapped"], stats["nulled"],
                " (dry run)" if dry_run else "")
    if dry_run:
        return

    for (target,), ids in changes.items():
        for i in range(0, len(ids), 100):
            chunk = ",".join(f'"{x}"' for x in ids[i:i + 100])
            _request(url, key, f"/rest/v1/events?id=in.({urllib.parse.quote(chunk)})",
                     "PATCH", {"subcategory": target}, prefer="return=minimal")


def deactivate_past_events(url: str, key: str, dry_run: bool) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=PAST_EVENT_GRACE_DAYS)).isoformat()
    # Ended events
    f1 = f"end_time=lt.{urllib.parse.quote(cutoff)}&is_active=eq.true"
    # No end_time and started before the cutoff
    f2 = f"end_time=is.null&start_time=lt.{urllib.parse.quote(cutoff)}&is_active=eq.true"
    n1, n2 = _count(url, key, f1), _count(url, key, f2)
    logger.info("past events to deactivate: %d ended, %d no-end-time%s",
                n1, n2, " (dry run)" if dry_run else "")
    if dry_run:
        return
    # Patch in id-chunks — a single UPDATE over tens of thousands of rows
    # (each firing the updated_at trigger) exceeds the PostgREST statement
    # timeout.
    for f in (f1, f2):
        total = 0
        while True:
            batch, _ = _request(url, key, f"/rest/v1/events?select=id&{f}&limit=200")
            if not batch:
                break
            ids = ",".join(f'"{r["id"]}"' for r in batch)
            for attempt in range(3):
                try:
                    _request(url, key, f"/rest/v1/events?id=in.({urllib.parse.quote(ids)})",
                             "PATCH", {"is_active": False}, prefer="return=minimal")
                    break
                except Exception as e:
                    if attempt == 2:
                        raise
                    logger.warning("  patch retry after: %s", e)
                    import time
                    time.sleep(2 * (attempt + 1))
            total += len(batch)
            if total % 5000 < 200:
                logger.info("  deactivated %d ...", total)
        logger.info("  deactivated %d total", total)


def run(dry_run: bool = False) -> None:
    url, key = _load_env()
    fix_categories(url, key, dry_run)
    fix_subcategories(url, key, dry_run)
    deactivate_past_events(url, key, dry_run)
    logger.info("done")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    run(dry_run=ap.parse_args().dry_run)
