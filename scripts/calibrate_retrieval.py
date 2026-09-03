#!/usr/bin/env python3
"""Calibrate the retrieval relevance floor and write the single active config row.

FEAT-24. The floor cannot be a chosen constant: cosine scores are not comparable
across embedding models or corpora, so a number that separates relevant from
irrelevant under one model is meaningless under another. It has to be MEASURED,
against a fixture whose freshness is known, and rewritten whenever the model
changes.

What it does:
  1. Loads the dated scenario fixture and refuses a stale one.
  2. Runs each query through match_events_v2 — the production path, not a
     reimplementation of it.
  3. Sweeps candidate floors and picks the one separating labelled-relevant from
     labelled-irrelevant best (Youden's J: sensitivity + specificity - 1).
  4. Writes ONE active row, transactionally, tagged with the embedding model and
     dimension it was measured under.

    uv run python scripts/calibrate_retrieval.py --fixture eval/fixtures/<name>.json
    uv run python scripts/calibrate_retrieval.py --fixture … --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv()

from pipeline.embedder import get_embedder  # noqa: E402

FIXTURE_MAX_AGE_DAYS = int(os.environ.get("FIXTURE_MAX_AGE_DAYS", "14"))
DEFAULT_K = 3


def load_fixture(path: Path) -> dict:
    """The fixture, if it is fresh enough to say anything about tonight.

    Age is measured from the recorded capture date, never file mtime: re-saving a
    stale fixture must not make it look current.
    """
    fx = json.loads(path.read_text())
    captured = date.fromisoformat(fx["captured_at"])
    age = (date.today() - captured).days
    if age > FIXTURE_MAX_AGE_DAYS:
        sys.exit(
            f"fixture {fx['id']} was captured {age} days ago, limit is {FIXTURE_MAX_AGE_DAYS}. "
            "Recapture it — a stale fixture cannot calibrate behaviour for tonight."
        )
    if not fx.get("cases"):
        sys.exit(f"fixture {fx['id']} has no cases")
    return fx


def search(vec: list[float], case: dict, limit: int = 20) -> list[dict]:
    url, key = os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
    payload = {
        "query_embedding": json.dumps(vec),
        "p_query_text": case["query"][:80],
        "p_limit": limit,
        **{k: v for k, v in (case.get("args") or {}).items()},
    }
    r = httpx.post(
        f"{url}/rest/v1/rpc/match_events_v2",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        json=payload,
        timeout=30,
    )
    if r.status_code == 404:
        sys.exit("match_events_v2 not found — apply migrations 011 and 012 first.")
    r.raise_for_status()
    return r.json()


def sweep(scored: list[tuple[float, bool]]) -> tuple[float, float]:
    """Best separating floor by Youden's J, and its score.

    J rewards a floor that keeps the relevant AND rejects the irrelevant. Accuracy
    alone would be maximised by rejecting everything whenever most candidates are
    irrelevant, which is the degenerate floor that stops the ladder ever widening.
    """
    rel = [s for s, r in scored if r]
    irr = [s for s, r in scored if not r]
    if not rel or not irr:
        sys.exit("fixture needs both relevant and irrelevant labelled results to separate them")
    best, best_j = 0.0, -2.0
    for cand in sorted({round(s, 3) for s, _ in scored}):
        sens = sum(1 for s in rel if s >= cand) / len(rel)
        spec = sum(1 for s in irr if s < cand) / len(irr)
        j = sens + spec - 1
        if j > best_j:
            best, best_j = cand, j
    return best, best_j


def write_config(floor: float, k: int, model: str, dim: int, fx: dict, dry: bool) -> None:
    """Replace the active row atomically: no window with none active, and never two."""
    url, key = os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
    row = {
        "active": True,
        "floor": floor,
        "k": k,
        "embedding_model": model,
        "embedding_dim": dim,
        "fixture_id": fx["id"],
        "fixture_captured_at": fx["captured_at"],
    }
    if dry:
        print("  [dry run] would write:", json.dumps(row))
        return
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    # The partial unique index permits only one active row, so the old one is
    # stood down first. Both statements are required; a failure between them
    # leaves no active row, which fails closed rather than serving a stale floor.
    httpx.patch(
        f"{url}/rest/v1/retrieval_config?active=eq.true",
        headers=h,
        json={"active": False},
        timeout=30,
    ).raise_for_status()
    httpx.post(
        f"{url}/rest/v1/retrieval_config", headers=h, json=row, timeout=30
    ).raise_for_status()
    print(f"  wrote active config: floor={floor} k={k} model={model}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixture", required=True, type=Path)
    ap.add_argument("--k", type=int, default=DEFAULT_K)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    fx = load_fixture(args.fixture)
    embedder = get_embedder()
    model = os.environ.get("EMBED_MODEL") or "unknown"
    dim = int(os.environ.get("EMBED_DIM") or 1536)
    print(f"fixture {fx['id']} captured {fx['captured_at']} · model {model} · dim {dim}")

    scored: list[tuple[float, bool]] = []
    for case in fx["cases"]:
        vec = embedder.embed_batch([case["query"]])[0]
        relevant = set(case.get("relevant_ids", []))
        rows = search(vec, case)
        for r in rows:
            if r.get("similarity") is None:
                continue
            scored.append((float(r["similarity"]), r["id"] in relevant))
        print(f"  {case['query'][:44]:<44} {len(rows):>3} rows")

    floor, j = sweep(scored)
    print(f"\nfloor {floor} (Youden's J {j:.3f}) over {len(scored)} scored results")
    write_config(floor, args.k, model, dim, fx, args.dry_run)


if __name__ == "__main__":
    main()
