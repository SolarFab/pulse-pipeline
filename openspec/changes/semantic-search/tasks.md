# Tasks — Semantic Search / Concierge Tools

Depends on: `event-embeddings` (pgvector column + backfill) and the taxonomy table (§1 of
`unify-taxonomy`). All code tasks live in the **web repo (`nachtkarte`)** unless marked.

## 1. Retrieval foundation

- [ ] 1.1 [db] SQL function or query for hybrid search: strict WHERE (active, upcoming, dates, category, facets, venue ilike, price) + optional `embedding <=> $qvec` ordering, LIMIT ≤ 20
- [ ] 1.2 [web] Server-side query embedding via the OpenRouter gateway (same env config as pipeline); assert model id matches `events.embed_model`, else log + filter-only fallback
- [ ] 1.3 [web] Verify anon-key/RLS posture: chat reads public events only

## 2. Tools

- [ ] 2.1 [web] `search_events` tool: zod schema (category/subcategory enums generated from the taxonomy table), all params optional, compact result shape (no descriptions)
- [ ] 2.2 [web] Geo params: lat+lng-together validation, radius default/clamp, haversine filter + distance ordering, `distance_km` in results
- [ ] 2.3 [web] `get_event_details` tool: full row by id
- [ ] 2.4 [web] Unit tests: arg validation (incl. incomplete geo), hard-constraint SQL (no paid event passes `free_entry`), facet-true-only semantics, unknown-price inclusion, ordering priority (query > distance > start_time)

## 3. Chat loop

- [ ] 3.1 [web] Rewrite `chat/route.ts` on Vercel AI SDK `streamText` + `tools`, bounded steps; delete keyword/genre tables (completes `unify-taxonomy` §3.2)
- [ ] 3.2 [web] System prompt: Berlin current time, grounding rules (tool results only, honest empty-result behaviour), untrusted-data rule for descriptions
- [ ] 3.3 [web] Failure paths: embedding down → filter-only; tool error → brief error string to model
- [ ] 3.4 [web] Keep streaming UX identical for the existing chat UI

## 3b. Dialog policy & personalization

- [ ] 3b.1 [web] Draft the three policy variants (always-answer-broad / answer-then-offer-refinement / clarify-when-broad) as prompt snippets
- [ ] 3b.2 [web] Profile context injection for signed-in users (onboarding categories, Kiez, family status; anon-key + JWT read of own profile); bias-not-exclude rule + explicit-ask-wins in the prompt
- [ ] 3b.3 [web] Anonymous users: verify neutral prompt (no profile line)

## 4. Quality

- [ ] 4.1 [web] Injection test: adversarial description in a fixture event does not alter behaviour
- [ ] 4.2 [pipeline] Reuse the benchmark golden queries as a retrieval eval against `search_events` (are the right events in top-5?)
- [ ] 4.3 [web] Verify end-to-end with the webapp-testing skill: "jazz tonight", "kostenlos am Sonntag draußen", "was geht im SchwuZ", empty-result case
- [ ] 4.4 Log per turn: tools called, result counts, latency, tokens (basis for later evals)
- [ ] 4.5 Prompt benchmark (promptfoo): golden dialog set (~20 cases incl. broad/ambiguous/explicit-ask/profile cases), deterministic tool-arg assertions + LLM-rubric grounding/policy checks, grid = prompt variants (zero-shot, few-shot, +reasoning, policy variants) × ≥2 chat models via OpenRouter; document results in docs/, ship the winner
- [ ] 4.6 Wire the prompt benchmark as the regression gate for any future prompt/model change

## 5. Ship

- [ ] 5.1 [web] Feature branch + preview deploy; side-by-side sanity check vs old chat
- [ ] 5.2 [web] Merge after review; keep the old code path deletable in one revert

## v1.1 (deferred — needs preference-feed interaction log)
- [ ] 6.1 [web] `save_event` write tool (bookmark from chat, auth-gated) + interaction logging
