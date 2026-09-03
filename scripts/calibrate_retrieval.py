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
    judged = sum(
        1
        for c in fx["cases"]
        for cand in c.get("candidates", [])
        if cand.get("relevant") is not None
    )
    if judged == 0:
        sys.exit(
            f"fixture {fx['id']} carries no judgements. Run scripts/capture_fixture.py, "
            "label each candidate true or false, then calibrate. Labels cannot be "
            "invented: a floor measured against a guess looks calibrated and is not."
        )
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
        sys.exit("match_events_v2 not found — apply migrations 013 and 014 first.")
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
    # Credentials are read only on the writing path: a dry run must work with none,
    # or it cannot run anywhere the real thing must not — CI included.
    url, key = os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    # The database function performs the deactivate + insert in one transaction.
    # Keeping both statements behind one RPC is the only way a failed request can
    # leave the previous active configuration intact.
    httpx.post(
        f"{url}/rest/v1/rpc/set_active_retrieval_config",
        headers=h,
        json={
            "p_floor": row["floor"],
            "p_k": row["k"],
            "p_embedding_model": row["embedding_model"],
            "p_embedding_dim": row["embedding_dim"],
            "p_fixture_id": row["fixture_id"],
            "p_fixture_captured_at": row["fixture_captured_at"],
        },
        timeout=30,
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
    # The CONCRETE model, taken from the embedder that actually produced the
    # vectors — never the env var, which is absent by default while
    # get_embedder() still selects a real default. Recording "unknown" made every
    # later comparison vacuous, so a model change could not invalidate the floor.
    model = getattr(embedder, "model", None) or ""
    if not model:
        sys.exit("embedder exposes no model name — cannot record what the floor was measured under")
    dim = int(os.environ.get("EMBED_DIM") or 1536)
    print(f"fixture {fx['id']} captured {fx['captured_at']} · model {model} · dim {dim}")

    scored: list[tuple[float, bool]] = []
    for case in fx["cases"]:
        # Judgements are the fixture's, not this run's: re-searching would compare
        # today's results against yesterday's labels and silently mislabel both.
        judged = {
            c["id"]: c["relevant"]
            for c in case.get("candidates", [])
            if c.get("relevant") is not None
        }
        vec = embedder.embed_batch([case["query"]])[0]
        rows = search(vec, case)
        for r in rows:
            if r.get("similarity") is None or r["id"] not in judged:
                continue
            scored.append((float(r["similarity"]), bool(judged[r["id"]])))
        print(f"  {case['query'][:44]:<44} {len(rows):>3} rows, {len(judged)} judged")

    floor, j = sweep(scored)
    print(f"\nfloor {floor} (Youden's J {j:.3f}) over {len(scored)} scored results")
    write_config(floor, args.k, model, dim, fx, args.dry_run)


if __name__ == "__main__":
    main()
