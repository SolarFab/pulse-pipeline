# Tasks — Preference Feed

Each task notes whether it touches the **[web]** app (Next.js/TS), the **[pipeline]** (Python),
or the **[db]** (Supabase migration).

## 1. Embeddings foundation

- [x] 1.1 [db] Supabase migration: enable `pgvector`; add `events.embedding vector(N)` + `events.embed_model text` + HNSW index
- [x] 1.2 [pipeline] Add a swappable embedder module (config-selected model) with a stable text builder (title + description + category + tags)
- [x] 1.3 [pipeline] Embed each event on upsert; skip re-embed when embed-relevant text is unchanged
- [x] 1.4 [pipeline] One-off backfill script to embed all existing active events; verify no active event has a null embedding

## 2. Taste model

- [ ] 2.1 [db] Migration: `user_taste(user_id, embedding vector(N), updated_at)` + `interaction_log(user_id, event_id, action, ts)`; enable RLS + owner policies on both
- [ ] 2.2 [web/pipeline] Function to (re)compute a user's taste vector = recency-weighted mean of liked/going/interested-venue embeddings minus dismissed
- [ ] 2.3 [web] Update the taste vector incrementally when a signal changes (like/going/dismiss); add a nightly consolidation job
- [ ] 2.4 [web] Cold-start path: derive an initial taste from onboarding categories/vibes when no likes exist

## 3. Ranking + feed API

- [ ] 3.1 [web] `/api/feed` endpoint: hybrid score = w·cosine(taste, event) + freshness + proximity, over active upcoming events, via the anon-key client (RLS on)
- [ ] 3.2 [web] Add the exploration quota (10–20% novel/diverse items) to each feed page
- [ ] 3.3 [web] Fallback ranking (popular + nearby) for users with no taste at all

## 4. Feed UI

- [ ] 4.1 [web] New "For You" Feed tab that renders the ranked list with existing event cards
- [ ] 4.2 [web] Like / going / dismiss actions on feed cards wired to `user_events` + interaction log
- [ ] 4.3 [web] (Optional) cached "why we picked this" line built only from structured event fields

## 5. Learning loop

- [ ] 5.1 [web] Log sampled feed interactions (impression, open, dismiss) to `interaction_log`
- [ ] 5.2 [web] Feed the interaction signals back into the taste recompute (dismiss down-weights similar events)

## 6. Privacy & security

- [ ] 6.1 [db/web] Verify all per-user reads/writes use the anon key + JWT; confirm `service_role` is never on the request path
- [ ] 6.2 [db] Test cross-user isolation: user A cannot read user B's taste/interactions/bookmarks
- [ ] 6.3 [web] Account deletion removes `user_taste` + `interaction_log` rows
- [ ] 6.4 [web] Add the "we analyze your interactions to personalize" clause to the Datenschutz page

## 7. Evaluation & tuning

- [ ] 7.1 [pipeline] Build a small offline eval set (held-out likes) to score ranking quality (precision@k)
- [ ] 7.2 [web] Tune the score weights (cosine/freshness/proximity) + exploration ratio against the eval set
- [ ] 7.3 Ship behind a feature flag; dogfood; then enable by default
