# Design — Preference Feed

## Context

Pulse already stores per-user signals (`profiles`, `user_events`, `interested_venues`) and an
`event_interest_counts` view, but has no ranking layer. The database is Supabase Postgres +
PostGIS; there is no `pgvector` yet. The feed must be fast (runs on every scroll), cheap
(no LLM on the hot path), and multi-tenant-safe (per-user data behind RLS). This design also
lays the `event-embeddings` foundation that the future `semantic-search` capability reuses.

## Goals / Non-Goals

**Goals:** a personalized, upcoming-events feed that ranks by learned taste + time + place;
a cheap, explainable learning loop; a reusable event-embedding layer.

**Non-Goals:** collaborative filtering / social recommendations; any LLM in the ranking path;
selling or exposing person-level taste data; the concierge semantic search (separate change).

## Decisions

- **Content-based taste vector, not collaborative filtering.** Single city, cold-start-heavy,
  and far simpler/explainable. *Alternative:* CF ("users like you") — needs scale we don't have
  and worse cold start.
- **pgvector, not a dedicated vector DB.** Events already live in Postgres; one query joins
  vectors + SQL filters (date/price/geo). *Alternative:* Pinecone/Chroma — extra infra, sync
  burden, no ACID with our relational data.
- **Taste = recency-weighted mean of liked embeddings − dismissed embeddings.** Cheap, updatable
  incrementally, explainable. *Alternative:* train a per-user model — overkill at this stage.
- **Hybrid score = w·cosine + freshness + proximity, plus a 10–20% exploration quota.** Pure
  vector similarity ignores that events are time- and place-bound. Weights are configurable and
  tuned against an offline eval set.
- **Swappable embedder behind config** (start `text-embedding-3-small` or an open model like
  `bge`); store the model id per event so a model swap triggers re-embed. Keeps us model-agnostic.
- **Per-user data via the anon key + user JWT so RLS applies.** The `service_role` key is
  server-only (migrations/admin). This is the load-bearing security decision (OWASP LLM02/data).
- **Taste recomputed incrementally on each signal + a nightly consolidation job**, not per
  request. *Alternative:* per-request recompute — too slow/expensive on the hot path.

## Risks / Trade-offs

- **Filter bubble** → the 10–20% exploration quota + diversity across categories/venues.
- **Cold start** → onboarding categories first, then popular/nearby fallback.
- **Embedding-model drift** → record model id per event; backfill on change.
- **Behaviour-log row explosion** → sample impressions (not every pixel) + retention window.
- **RLS misconfiguration / `service_role` leak** → server-only key from a secret; explicit
  `enable row level security` + policies on every per-user table; test cross-user isolation.
- **pgvector recall/latency at scale** → HNSW index; fine at current scale, revisit at 100k+.

## Migration Plan

1. Supabase migration (via Supabase CLI, versioned): enable `pgvector`; add `events.embedding`
   + ANN index; create `user_taste` and `interaction_log`; enable RLS + owner policies.
2. Pipeline: embed on ingest; run the one-off backfill for existing events.
3. Web: ship the Feed tab behind a feature flag; dogfood; then enable by default.
4. **Rollback:** all schema changes are additive (new columns/tables), so rollback = hide the
   Feed tab + stop embedding; no destructive change to existing data.

## Open Questions

- Final embedder + dimension (OpenAI `text-embedding-3-small` vs. open `bge-m3`/`nomic`)?
- Exploration algorithm: pure random vs. diversity/MMR-based?
- Real-time vs. nightly taste recompute threshold (how many signals before re-consolidation)?
- Weight-tuning: manual vs. a small offline eval set with held-out likes?

## Decision log

- **2026-07-30 — Embedder = `openai/text-embedding-3-small` via OpenRouter, `vector(1536)`.**
  Experiment 1 (docs/EXPERIMENT.md): hand-labeled qrels over the frozen corpus gave
  R@5 0.776 / MRR 0.78 / nDCG@5 0.716 vs qwen3-embedding-8b at 0.246 / 0.453 / 0.262 —
  decisive despite near-tied proxy metrics (which alone would have misjudged). Results:
  `eval/results/qrels_scores_v1.json`, `docs/embedding-benchmark-qrels.md`.
