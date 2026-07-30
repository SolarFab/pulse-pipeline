#!/usr/bin/env python3
"""One-off backfill: facets + embeddings for active UPCOMING events (preference-feed 1.4,
unify-taxonomy 2.3).

Scope: is_active AND start_time >= now AND embedding IS NULL. Past events are skipped —
they never rank in the feed; the nightly scrape embeds everything new going forward.

Usage:
    python scripts/backfill_embeddings.py --dry-run    # counts + cost estimate only
    python scripts/backfill_embeddings.py              # do it

Writes eval/results/backfill-<ts>.json (events, tokens, USD, latency) — the cost/latency
evidence for the showcase.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

from tenacity import retry, stop_after_attempt, wait_exponential  # noqa: E402

from db.supabase import get_client  # noqa: E402
from pipeline.embed_events import PRICE_PER_MTOK, attach_embeddings  # noqa: E402
from pipeline.embedder import DEFAULT_MODELS, build_embed_text  # noqa: E402
from pipeline.facets import detect_facets  # noqa: E402

BATCH = 100
ROOT = Path(__file__).resolve().parent.parent


def fetch_page(client, now_iso: str, offset: int) -> list[dict]:
    return (
        client.table("events")
        .select("id,title,description,category,subcategory,tags,price,price_cents,fingerprint")
        .eq("is_active", True).gte("start_time", now_iso).is_("embedding", "null")
        .order("start_time", desc=False).range(offset, offset + BATCH - 1)
        .execute().data or []
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    client = get_client()
    now_iso = datetime.now(UTC).isoformat()
    total = {"events": 0, "embedded": 0, "skipped": 0, "failed": 0,
             "tokens": 0, "usd": 0.0, "embed_seconds": 0.0}
    t_start = time.time()

    if args.dry_run:
        # count + token estimate without any API call
        n, est_tokens, offset = 0, 0, 0
        while True:
            page = fetch_page(client, now_iso, offset)
            if not page:
                break
            n += len(page)
            est_tokens += sum(len(build_embed_text(e)) // 4 for e in page)
            offset += BATCH
        model = DEFAULT_MODELS["openrouter"]
        print(f"DRY RUN: {n} upcoming active events lack embeddings")
        print(f"  est. tokens: {est_tokens:,}  est. cost: "
              f"${est_tokens / 1e6 * PRICE_PER_MTOK.get(model, 0.02):.4f}  model: {model}")
        return

    offset_guard = 0
    while True:
        page = fetch_page(client, now_iso, 0)  # embedding turns non-null as we go; always page 0
        if not page:
            break
        offset_guard += 1
        if offset_guard > 500:  # safety: never loop forever
            print("! page guard tripped — aborting")
            break

        m = attach_embeddings(page)  # no db_hashes needed: these rows have no embedding yet
        for k in ("embedded", "skipped", "failed", "tokens", "usd"):
            total[k] += m[k]
        total["embed_seconds"] += m["seconds"]

        @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=1, max=15))
        def _update(row_id: str, payload: dict) -> None:
            # transient HTTP/2 stream resets from the REST gateway are common on
            # long runs — retry with backoff instead of dying mid-backfill
            client.table("events").update(payload).eq("id", row_id).execute()

        for e in page:
            if "embedding" not in e:
                continue
            facets = detect_facets(e)
            try:
                _update(e["id"], {
                    "embedding": e["embedding"], "embed_model": e["embed_model"],
                    "embed_hash": e["embed_hash"], **facets,
                })
                total["events"] += 1
            except Exception as exc:
                total["failed"] += 1
                print(f"  ! update failed after retries for {e['id']}: {type(exc).__name__}")
        print(f"  +{m['embedded']} embedded (total {total['events']}, "
              f"{total['tokens']:,} tok, ${total['usd']:.4f})")
        if m["embedded"] == 0:  # nothing embeddable left in this page (all failed) — stop
            break

    total["wall_seconds"] = round(time.time() - t_start, 1)
    total["usd"] = round(total["usd"], 6)
    total["events_per_second"] = round(total["events"] / total["wall_seconds"], 1) if total["wall_seconds"] else 0
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = ROOT / "eval" / "results" / f"backfill-{stamp}.json"
    out.write_text(json.dumps({"run": "backfill-facets-embeddings", "scope": "active upcoming",
                               "model": DEFAULT_MODELS["openrouter"], **total}, indent=2))
    print(f"\nDone: {total['events']} events · {total['tokens']:,} tokens · "
          f"${total['usd']:.4f} · {total['wall_seconds']}s wall "
          f"({total['embed_seconds']:.1f}s embedding API)")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
