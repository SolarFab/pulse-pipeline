# Preference Feed

## Why

Pulse already collects rich preference signals — onboarding taste in `profiles`, `user_events` (interested/going), `interested_venues` — and the onboarding even promises *"the more you explore, the smarter your feed gets."* But there is no feed and no ranking engine, so those signals go unused and every user sees the same unranked list. This introduces a personalized **"For You" feed** that ranks upcoming events per user and learns from behaviour.

## What Changes

- New **Feed tab ("For You")** that ranks upcoming events for the signed-in user.
- A per-user **taste vector** (embedding) built from liked/going events, interested venues, and onboarding categories; recomputed as signals change.
- **pgvector** enabled on Supabase; each event embedded **once at ingest** (a shared foundation also used later by semantic search).
- Ranking = cosine similarity to the taste vector, boosted by **freshness** and **proximity**, with **10–20% exploration** (novel/diverse events) to avoid a filter bubble.
- **Sampled behaviour logging** (feed impressions, opens, dismissals) that nudges the taste vector — the "learning" loop.
- Optional, **cached** "why we picked this" one-liner per card (cheap LLM, built only from structured event fields — not the ranking engine).
- Explicitly **not an agent**: ranking is vector math + SQL.

## Capabilities

### New Capabilities
- `event-embeddings` — enable pgvector and embed every event (with a swappable embedder). Foundation shared with future `semantic-search`.
- `preference-feed` — the taste vector, the ranking, the interaction-logging loop, and the Feed tab + `/api/feed` endpoint.

### Modified Capabilities
- None. Existing `user_events` bookmark behaviour is reused, not changed.

## Impact

- **Database (Supabase):** enable `pgvector`; add `events.embedding vector`, `user_taste(user_id, embedding, updated_at)`, and a sampled `interaction_log(user_id, event_id, action, ts)`. RLS required on every per-user table (queried via the **anon key + user JWT**, never `service_role`).
- **Pipeline (Python):** embed each event at ingest via a swappable embedder; one-off backfill of existing (~1,000) events.
- **Web (Next.js/TS):** new Feed tab, `/api/feed` ranking endpoint, client-side interaction logging (sampled).
- **Cost:** embeddings are ~pennies (once per event); ranking is free (vector + SQL). The optional "why" blurb is one cached LLM call per event.
- **Privacy / GDPR:** a per-user taste vector is personal data → needs consent + deletion, stays **internal** (person-level never sold); add a line to the Datenschutz ("we analyze your interactions to personalize recommendations").
- **Security (OWASP LLM Top 10):** LLM01 minimal — the feed does not feed untrusted scraped text to a model (the optional blurb uses only structured fields). LLM02/data — per-user rows protected by RLS + anon key. No new injection surface.

## Non-goals

- **Not** the concierge semantic search (separate `semantic-search` capability, though it reuses `event-embeddings`).
- **Not** LLM-in-the-loop ranking — no agent, no model call on the hot path.
- **Not** collaborative filtering / social ("people like you") — v1 is content-based on *your own* taste.
- **Not** selling or exposing person-level taste data; only aggregated demand signals are shareable (out of scope here).
