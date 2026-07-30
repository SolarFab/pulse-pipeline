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

```ts
search_events({
  query?: string,            // free text, embedded server-side; omit for pure filter queries
  category?: Category,       // enum GENERATED from the canonical taxonomy table
  subcategory?: Subcategory, // enum generated likewise
  date_from?: string, date_to?: string,   // ISO; model resolves "tonight" from system prompt
  neighborhood?: string, venue?: string,  // venue: fuzzy ilike match
  family_friendly?: boolean, outdoor?: boolean, free_entry?: boolean,
  max_price_cents?: number,
  limit?: number             // default 10, max 20
}) -> [{ id, title, venue_name, start_time, category, subcategory, price, neighborhood }]

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
