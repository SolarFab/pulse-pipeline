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
