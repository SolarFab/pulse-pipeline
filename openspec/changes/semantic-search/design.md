# Design — Semantic Search / Concierge Tools

## Control flow (and why no framework)

```
user msg ─► /api/chat (Vercel AI SDK, streamText + tools, maxSteps≈4)
                │
                ├─ model may call search_events(args)
                │      │  validate args (zod) ─► if query: embed via gateway
                │      │  ─► SQL: filters AND (embedding <=> qvec) ranking ─► compact rows
                │      └─ result streamed back into the loop (DATA, not instructions)
                ├─ model may call get_event_details(id)
                └─ model answers, grounded in tool results only
```

One decision point, no branching state — native AI SDK tool loop, not LangGraph (see AGENTS.md:
agent only where it earns it). `maxSteps` bounds runaway loops; typical turn = 1 search + answer.

## Tool contracts (v1 — final shapes live in code, zod-validated)

Every parameter is optional — the model composes exactly the constraints the question contains.
Two kinds of parameters: **filters** constrain (strict SQL, never soft); **`query` ranks** (orders
the allowed set, never excludes).

```ts
search_events({
  query?: string,            // RANKS (the only non-filter): embedded server-side, cosine ordering
  category?: Category,       // filter; enum GENERATED from the canonical taxonomy table
  subcategory?: Subcategory, // filter; enum generated likewise
  date_from?: string, date_to?: string,   // filter; ISO; model resolves "tonight" itself.
                                          // default window: now -> +14 days
  neighborhood?: string,     // filter; our column granularity ("Neukölln")
  venue?: string,            // filter; fuzzy ilike
  family_friendly?: boolean, // filters ONLY when true (require); omitted = don't care.
  outdoor?: boolean,         //   never false-means-exclude: detection is conservative
  free_entry?: boolean,      //   (false negatives), so exclusion would lie
  max_price_cents?: number,  // filter; excludes events KNOWN to cost more; unknown price stays in
  lat?: number, lng?: number,   // filter+rank; lat+lng together or not at all; source: model
  radius_km?: number,           //   world knowledge or client user-location, NEVER scraped text.
                                //   default 1.5, clamped 0.2–10
  limit?: number             // default 10, max 20
}) -> [{ id, title, venue_name, start_time, category, subcategory, price, neighborhood,
         distance_km? /* only when geo was given; similarity scores are NOT returned */ }]
```

Ordering priority (deterministic): `query` present → similarity; else geo present → distance;
else → `start_time`. Filters always apply first; ranking orders within the allowed set.

get_event_details({ event_id: string })
  -> { ...full row incl. description, source_url, lat/lng }
```

Compact-then-drill: search returns no descriptions (token cost, injection surface); the model
fetches details only when needed.

## Hybrid retrieval semantics

- `query` present → candidate set = structured filters (SQL WHERE on active, upcoming, category,
  dates, facets, price) → ranked by cosine distance to the query embedding (pgvector, same model
  as event embeddings — the benchmark winner, read from config).
- No `query` → filters only, ordered by `start_time`.
- Hard constraints are **never** soft: a date range or `free_entry=true` filters, it doesn't just
  boost. Semantic ranking orders *within* the allowed set.
- Query embedding via the same OpenRouter gateway + model as ingest (env-config; a mismatch of
  embedding models would silently break retrieval — assert model id matches `events.embed_model`).

## Grounding & untrusted input (LLM01)

- System prompt: answer **only** from tool results; if empty, say so and suggest relaxing a
  constraint — never invent events from world knowledge (keeps today's honest-fallback behaviour).
- Tool results are wrapped as data; descriptions are scraped text and may contain adversarial
  strings — the prompt states they are content, never instructions, and no tool argument is ever
  derived from a previous tool result's free text without the model's explicit reasoning.
- Read-only v1: worst-case injection outcome is a bad answer, not a bad action.

## Model-agnostic

Chat model behind the Vercel AI SDK provider config; embedding calls behind the same env-driven
gateway as the pipeline (`EMBED_PROVIDER`/`EMBED_MODEL`). No provider names in route logic.

## Failure modes

- Embedding call fails → fall back to filter-only search (degraded, not broken), log it.
- Tool SQL fails → the model receives an error string and apologises honestly; never a stack trace
  to the user.
- Model never calls a tool (chit-chat) → fine; no forced tool use.

## Observability (minimal)

Log per turn: tools called, arg summary (no user PII beyond the query), result counts, latency,
token usage. Enough to eval retrieval quality later against the golden queries.

## Decision log

- **2026-07-30 — Retrieval mode = vector-only (baseline).** Experiment 2 (retrieval ladder on
  qrels **v2** — semantic-only labeling guideline, pool bias fixed via delta round, LLM
  expansions pinned): baseline R@5 0.621 / P@5 0.585 / **MRR 0.896** / nDCG@5 0.729 @ ~750ms
  beats Multi-Query (0.531/0.653/0.540), hybrid BM25+RRF (0.458/0.755/0.542), HyDE
  (0.370/0.596/0.428) and BM25-only (0.392/0.546/0.380 @ 2ms) on every metric. Latency for
  MQ/HyDE measured uncached at 2.1–2.6s/query — busts the ~2s chat budget (cached-run
  latencies exclude the LLM call and must not be quoted). HyDE's riester-kompass win does NOT
  replicate here. Methodology notes: (1) uncached MQ/HyDE scores varied run-to-run (HyDE R@5
  0.28–0.45) — LLM-dependent retrieval configs MUST pin their expansions; (2) qrels v1's
  date-aware judgments on temporal queries were corrected to semantic-only in v2 (dates are
  SQL filters, judged at the chat layer). `search_events` ships with pure pgvector cosine
  ranking inside hard SQL filters; revisit only with evidence (venue-name misses → BM25
  fusion first). Per-query choices + answer key: docs/showcase/retrieval-comparison.html.

- **2026-07-30 — System prompt = few-shot (worked examples); dialog policy = answer-first.**
  Experiment 3 stage 1 (tool-call accuracy, 13 golden chat queries, deterministic asserts,
  temp 0): few-shot 13/13 (haiku-4.5) / 12/13 (gpt-4o-mini) beats prod-v1 rules-only (10/9),
  zero-shot (11/9) and clarify-first (5/4). Findings: (1) worked examples fix exactly the
  hard cases — kiez→geo (q14) and relative-date resolution (q23) failed in every variant
  without examples; (2) clarify-first collapsed by refusing to search even fully-specified
  requests (free open-air cinema, rap, kids weekend) — over-clarification is a real failure
  mode, answer-first confirmed by data; (3) rules-only prod-v1 was no better than zero-shot —
  rules tell, examples teach. Cost: ~+600 prompt tokens/turn for +23pp accuracy on haiku
  (~$0.0005/turn) — shipped. Stage 2 (grounded end-to-end + judge) pending on the winner.

- **2026-07-31 — Prompt grid extended to 3 models + cost axis; few-shot wins on EVERY model.**
  few-shot: gpt-4o-mini 13/13 @ $0.00015/turn, gemini-2.5-flash 12/13 @ $0.00037 (fastest,
  ~900ms), claude-haiku-4.5 12/13 @ $0.00225. Pareto frontier = 4o-mini (zero-shot cheap
  corner, few-shot top). haiku is 15x the cost of 4o-mini at equal-or-lower tool accuracy —
  4o-mini is the CHAT_MODEL candidate, but stage 2 (answer quality/grounding/tone, judge)
  decides before switching. Kimi/Qwen/Llama blocked by the account's OpenRouter data policy
  (no provider matching restrictions) — pending user decision on a benchmark-only
  data_collection override. Run-to-run: haiku few-shot 13/13 -> 12/13 across runs at temp 0 —
  provider-side nondeterminism; scores carry ±1 case noise. Chart:
  docs/showcase/prompt-scatter.html (accuracy vs measured $/turn, Pareto frontier).

- **2026-07-31 — Full 9-model grid: Gemma-4-31B owns the Pareto frontier; few-shot generalizes.**
  36 cells. Top tier is a 6-way tie at 12/13 (92%) — few-shot on gpt-4o-mini/haiku/minimax-m2.7/
  deepseek-v4-pro/gemma-4-31b, prod-v1 on gemini-flash/gpt-4.1-nano; no 13/13 this run
  (±1-case provider nondeterminism, again). Frontier = gemma-4-31b zero-shot (85% @ $0.00006)
  and few-shot (92% @ $0.00012, 1.8s) — an OPEN 31B model matches the best closed models at
  1/20th of haiku's price. Latency splits the open field: gemma ~1.8s OK; minimax 4-7s and
  deepseek 5-8s bust the chat budget regardless of price. few-shot is best-or-tied on all 9
  models. CHAT_MODEL candidates for stage 2 (answer quality judge): gemini-2.5-flash
  (92% @ 841ms — latency champion) and gemma-4-31b (value champion); haiku no longer justified
  by this data alone. Chart: docs/showcase/prompt-scatter.html (color=model, shape=technique).

- **2026-07-31 — CHAT_MODEL = google/gemma-4-31b-it (stage-2 judge verdict).** End-to-end
  loop (real tools, real DB) on all 14 chat cases, judged by gpt-4o: gemma 14/14 on
  grounding/honesty/format/language AND resisted the planted injection (q20), 5.2s/turn,
  $0.012 total. haiku matched quality (14/14, inj ✓) at 7.7s and $0.097 — 8× the cost for
  nothing. gemini-2.5-flash — the stage-1 latency champion — FABRICATED events with invented
  IDs on thin-result cases (q16/q17/q20) and is disqualified: stage-1 tool-call accuracy did
  not predict grounding. gpt-4o-mini: 13/14 grounded. Shipped as the route default; env
  override remains. Evidence: eval/results/stage2-*.json, docs/stage2-benchmark.md.
