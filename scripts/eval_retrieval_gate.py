#!/usr/bin/env python3
"""Retrieval regression gate — semantic-search task 4.2.

Scores the hand-labelled golden queries against the **production** retrieval path
(`match_events`, the same RPC the web `search_events` tool calls), rather than against
an experimental config on a frozen corpus. `benchmark_retrieval.py` answers "which
technique is best"; this answers "did the shipped path get worse".

## The date window, and why it is pinned

The qrels were labelled on events running 30 July – 2 August 2026. `match_events`
defaults `p_date_from = now()`, so against production defaults **every labelled event is
already in the past and Recall@5 is 0 for every query, forever**. A gate that always
reads zero measures nothing.

So the window is derived at run time from the labelled events themselves — min/max
`start_time`, padded a day either side — which keeps the gate meaningful and keeps it
correct if the golden set is ever re-labelled against fresher events. The cost is that
this measures retrieval over a historical slice, not over tonight's catalogue. That is
the right trade for a regression gate: deterministic beats current.

Unlabelled results count as irrelevant (pool bias), the same convention
`benchmark_retrieval.py` uses.

## What this does and does not measure

It sends the query embedding, the window and a limit — nothing else. The real
`search_events` tool also passes category, subcategory and facet arguments that the model
infers from the conversation, and those narrow the candidate set considerably. So this is
the **retrieval floor**: how well pure vector search finds the labelled events. A drop here
is a real regression; a low absolute number is not by itself a product defect.

Usage:
    uv run python scripts/eval_retrieval_gate.py            # score and gate
    uv run python scripts/eval_retrieval_gate.py --report   # score, never fail

Exits non-zero when a metric falls below its floor, so CI can block on it.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import timedelta
from pathlib import Path

import httpx
from dateutil import parser as dateparser
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv()

from pipeline.embedder import get_embedder  # noqa: E402

QUERIES = ROOT / "eval" / "golden_set" / "v1.jsonl"
QRELS = ROOT / "eval" / "golden_set" / "qrels_v2.jsonl"
OUT_DIR = ROOT / "eval" / "results"
K = 5

# Floors, not targets — "do not get worse than today", set ~10% under the measured
# baseline so ordinary catalogue churn does not flap the build. Raise them when the
# path improves; never lower one to make a red build green.
#
# Baseline 2026-09-02: recall@5 0.232 · precision@5 0.246 · mrr 0.432 · ndcg@5 0.278
FLOORS = {"recall@5": 0.20, "mrr": 0.38, "ndcg@5": 0.25}


def load_golden() -> tuple[dict[str, str], dict[str, set[str]]]:
    """Query texts that apply to retrieval, and their relevant event ids."""
    queries = {}
    for line in QUERIES.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if "retrieval" in row.get("applies_to", []):
            queries[row["id"]] = row["query"]

    qrels: dict[str, set[str]] = {}
    for line in QRELS.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("relevant"):
            qrels.setdefault(row["query_id"], set()).add(row["event_id"])

    # Only score queries that have labels; an unlabelled query is not a failure.
    return {q: t for q, t in queries.items() if q in qrels}, qrels


def label_window(event_ids: set[str]) -> tuple[str, str]:
    """The span the golden set was labelled over, padded a day either side."""
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    resp = httpx.get(
        f"{url}/rest/v1/events",
        params={"id": f"in.({','.join(event_ids)})", "select": "start_time"},
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=30,
    )
    resp.raise_for_status()
    stamps = [dateparser.isoparse(r["start_time"]) for r in resp.json() if r.get("start_time")]
    if not stamps:
        sys.exit("None of the labelled events are in the database — re-label the golden set.")
    return (
        (min(stamps) - timedelta(days=1)).isoformat(),
        (max(stamps) + timedelta(days=1)).isoformat(),
    )


def search(query_vec: list[float], date_from: str, date_to: str) -> list[str]:
    """The production path: same RPC the web search_events tool calls."""
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    resp = httpx.post(
        f"{url}/rest/v1/rpc/match_events",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        json={
            "query_embedding": json.dumps(query_vec),
            "p_date_from": date_from,
            "p_date_to": date_to,
            "p_limit": K,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return [row["id"] for row in resp.json()]


def ndcg_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    dcg = sum(1 / math.log2(i + 2) for i, e in enumerate(ranked[:k]) if e in relevant)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(relevant))))
    return dcg / ideal if ideal else 0.0


def score(ranked: list[str], relevant: set[str]) -> dict[str, float]:
    hits = [e for e in ranked[:K] if e in relevant]
    rr = next((1 / (i + 1) for i, e in enumerate(ranked) if e in relevant), 0.0)
    return {
        "recall@5": len(hits) / len(relevant) if relevant else 0.0,
        "precision@5": len(hits) / K,
        "mrr": rr,
        "ndcg@5": ndcg_at_k(ranked, relevant, K),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", action="store_true", help="score without failing on a regression")
    args = ap.parse_args()

    queries, qrels = load_golden()
    if not queries:
        sys.exit("No labelled retrieval queries found.")

    all_labelled = {e for ids in qrels.values() for e in ids}
    date_from, date_to = label_window(all_labelled)
    print(f"{len(queries)} queries · window {date_from[:10]} → {date_to[:10]}\n")

    embedder = get_embedder()
    vectors = embedder.embed_batch([queries[q] for q in queries])

    per_query, totals = {}, {"recall@5": 0.0, "precision@5": 0.0, "mrr": 0.0, "ndcg@5": 0.0}
    for (qid, text), vec in zip(queries.items(), vectors, strict=True):
        ranked = search(vec, date_from, date_to)
        metrics = score(ranked, qrels[qid])
        per_query[qid] = {"query": text, "returned": len(ranked), **metrics}
        for k in totals:
            totals[k] += metrics[k]
        flag = " " if metrics["recall@5"] > 0 else "!"
        print(
            f"  {flag} {qid}  R@5 {metrics['recall@5']:.2f}  nDCG {metrics['ndcg@5']:.2f}  {text}"
        )

    mean = {k: v / len(queries) for k, v in totals.items()}
    print("\n" + "  ".join(f"{k} {v:.3f}" for k, v in mean.items()))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "retrieval-gate.json"
    out.write_text(
        json.dumps({"window": [date_from, date_to], "mean": mean, "per_query": per_query}, indent=2)
    )
    print(f"wrote {out.relative_to(ROOT)}")

    failed = [f"{k} {mean[k]:.3f} < {floor}" for k, floor in FLOORS.items() if mean[k] < floor]
    if failed and not args.report:
        sys.exit("\nRETRIEVAL REGRESSION: " + "; ".join(failed))
    if failed:
        print("\nbelow floor (reporting only): " + "; ".join(failed))


if __name__ == "__main__":
    main()
