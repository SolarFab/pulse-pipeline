#!/usr/bin/env python3
"""Embedding model benchmark (preference-feed: decides the embedder before task 1.1).

Part A — proxy labels: kNN precision@5 against category/subcategory labels over a
sample of real events. Both candidates see the identical sample.
Part B — mini golden set: German<->English queries; top-5 retrievals are PRINTED for
human verification (cross-lingual quality is the risk proxy labels can't measure).

Usage:
    python scripts/benchmark_embeddings.py                # all providers with keys
    python scripts/benchmark_embeddings.py --sample 300
    python scripts/benchmark_embeddings.py --providers openai
Writes docs/embedding-benchmark.md with the results table.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

from db.supabase import get_client  # noqa: E402
from pipeline.embedder import DEFAULT_MODELS, build_embed_text, get_embedder, has_key  # noqa: E402

# ── Part B: golden queries (DE<->EN). Correct answers are judged by a human. ──
GOLDEN_QUERIES = [
    "Jazzkonzert heute Abend",
    "jazz concert tonight",
    "Flohmarkt am Sonntag",
    "vintage flea market",
    "Techno Party in Neukölln",
    "underground electronic music",
    "etwas mit Kindern unternehmen",
    "fun activities for kids",
    "Ausstellung zeitgenössische Kunst",
    "free open air cinema",
    "Yoga im Park",
    "learn something new workshop",
]

K = 5


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def knn_precision(vecs: list[list[float]], labels: list[str | None], k: int = K) -> float:
    """Mean fraction of each item's k nearest neighbours sharing its label."""
    scored = 0
    total = 0.0
    for i, (v, lab) in enumerate(zip(vecs, labels)):
        if not lab:
            continue
        sims = [(cosine(v, w), labels[j]) for j, w in enumerate(vecs) if j != i]
        sims.sort(key=lambda s: -s[0])
        top = [s for s in sims[:k] if s[1]]
        if not top:
            continue
        total += sum(1 for _, other in top if other == lab) / len(top)
        scored += 1
    return total / scored if scored else 0.0


def fetch_events(sample: int) -> list[dict]:
    client = get_client()
    resp = (
        client.table("events")
        .select("id,title,description,category,subcategory,tags")
        .eq("is_active", True)
        .not_.is_("description", "null")
        .order("start_time", desc=False)
        .limit(sample)
        .execute()
    )
    return [e for e in resp.data if e.get("category")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=300)
    ap.add_argument("--providers", default=None, help="comma list; default: all with keys")
    args = ap.parse_args()

    providers = (
        args.providers.split(",")
        if args.providers
        else [p for p in DEFAULT_MODELS if has_key(p)]
    )
    if not providers:
        sys.exit("No provider API keys found (OPENAI_API_KEY / GEMINI_API_KEY). Nothing to do.")

    print(f"Fetching up to {args.sample} events…")
    events = fetch_events(args.sample)
    texts = [build_embed_text(e) for e in events]
    cats = [e.get("category") for e in events]
    subs = [e.get("subcategory") for e in events]
    print(f"{len(events)} events with a category. Providers: {providers}\n")

    rows = []
    query_sections = []
    for name in providers:
        emb = get_embedder(name)
        t0 = time.time()
        vecs = emb.embed_batch(texts)
        dt = time.time() - t0
        p_cat = knn_precision(vecs, cats)
        p_sub = knn_precision(vecs, subs)
        rows.append((name, emb.model, emb.dim, p_cat, p_sub, dt, len(texts)))
        print(f"{name:8} p@{K} category={p_cat:.3f}  subcategory={p_sub:.3f}  ({dt:.1f}s)")

        # Part B — print retrievals for human judgment
        qvecs = emb.embed_batch(GOLDEN_QUERIES)
        lines = [f"\n### {name} ({emb.model}, dim={emb.dim})"]
        for q, qv in zip(GOLDEN_QUERIES, qvecs):
            sims = sorted(
                ((cosine(qv, v), events[j]) for j, v in enumerate(vecs)),
                key=lambda s: -s[0],
            )[:K]
            lines.append(f"\n**{q}**")
            for s, e in sims:
                lines.append(f"- {s:.3f} [{e.get('category')}/{e.get('subcategory')}] {e['title'][:70]}")
        query_sections.append("\n".join(lines))

    out = Path(__file__).resolve().parent.parent / "docs" / "embedding-benchmark.md"
    table = "\n".join(
        f"| {n} | {m} | {d} | {pc:.3f} | {ps:.3f} | {dt:.1f}s / {cnt} events |"
        for n, m, d, pc, ps, dt, cnt in rows
    )
    out.write_text(
        "# Embedding benchmark\n\n"
        f"Sample: {len(events)} active events with category labels. "
        f"Metric: kNN precision@{K} (do an event's nearest neighbours share its label?).\n\n"
        "| provider | model | dim | p@5 category | p@5 subcategory | time |\n"
        "|---|---|---|---|---|---|\n" + table + "\n\n"
        "## Golden-query retrievals (verify by hand)\n"
        "Cross-lingual DE<->EN probes — a human judges whether the top-5 are correct.\n"
        + "\n".join(query_sections) + "\n"
    )
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
