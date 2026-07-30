"""Embed-at-ingest (preference-feed 1.3): attach embeddings to event dicts before upsert.

Hash-skip: an event is only embedded when its embed-relevant text is new or changed
(sha256 of build_embed_text vs the hash stored in the DB). Failures degrade, never
block — an event without an embedding still upserts (it just doesn't rank in the
feed until the next run heals it).

Every call returns metrics (embedded/skipped counts, tokens, cost, seconds) — the
per-run record for cost/latency evaluation.
"""

from __future__ import annotations

import json
import logging
import os

from .embedder import build_embed_text, embed_text_hash, get_embedder, has_key

logger = logging.getLogger(__name__)

# USD per 1M tokens, by model id (gateway ids); used for the run-cost metric.
PRICE_PER_MTOK = {
    "openai/text-embedding-3-small": 0.02,
    "openai/text-embedding-3-large": 0.13,
}


def attach_embeddings(
    events: list[dict],
    db_hashes: dict[str, str] | None = None,
    embedder=None,
) -> dict:
    """Mutate `events`: set embedding/embed_model/embed_hash where (re)embedding is due.

    db_hashes: fingerprint -> stored embed_hash (skip when unchanged).
    Returns metrics: {embedded, skipped, failed, tokens, usd, seconds}.
    """
    metrics = {"embedded": 0, "skipped": 0, "failed": 0, "tokens": 0, "usd": 0.0, "seconds": 0.0}
    provider = (os.environ.get("EMBED_PROVIDER") or "openrouter").lower()
    if embedder is None and not has_key(provider):
        logger.warning("no %s key — skipping embeddings (events upsert without them)", provider)
        metrics["skipped"] = len(events)
        return metrics

    emb = embedder or get_embedder()
    todo: list[tuple[dict, str, str]] = []
    for e in events:
        text = build_embed_text(e)
        h = embed_text_hash(text)
        stored = (db_hashes or {}).get(e.get("fingerprint") or "")
        if stored == h:
            metrics["skipped"] += 1
            continue
        todo.append((e, text, h))

    if not todo:
        return metrics

    try:
        vecs = emb.embed_batch([t for _, t, _ in todo])
    except Exception as exc:
        logger.error("embedding batch failed (%s: %s) — events upsert without embeddings",
                     type(exc).__name__, exc)
        metrics["failed"] = len(todo)
        return metrics

    for (e, _, h), vec in zip(todo, vecs):
        e["embedding"] = json.dumps(vec)  # pgvector accepts '[…]' text input
        e["embed_model"] = emb.model
        e["embed_hash"] = h
        metrics["embedded"] += 1

    metrics["tokens"] = getattr(emb, "total_tokens", 0)
    metrics["seconds"] = round(getattr(emb, "total_seconds", 0.0), 2)
    metrics["usd"] = round(metrics["tokens"] / 1e6 * PRICE_PER_MTOK.get(emb.model, 0.02), 6)
    return metrics
