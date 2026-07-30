# Semantic Search (Concierge Tool-Calling)

## Why

The concierge currently works by **prompt-stuffing**: a hand-rolled keyword table guesses a
category from the user's message, a fixed query loads events, and the lot is pasted into the
prompt. Consequences: "jazz tonight" degrades to *all music* (the keyword table doesn't know
subcategories), anything the keyword table doesn't anticipate ("something chill after work",
Ethio-jazz) misses entirely, token cost grows with the event list, and the keyword table is
drifting copy #2 of the taxonomy.

With events embedded (`event-embeddings`, shipping via `preference-feed`), the model can instead
**call tools**: free text is matched by meaning (pgvector), hard constraints (dates, price, area,
facets) stay exact SQL, and the prompt carries only what the tools return.

## What Changes

- Replace prompt-stuffing in `web/api/chat` with **native tool-calling** via the Vercel AI SDK
  (model-agnostic gateway; explicitly **not** LangGraph — single tool-loop, no graph).
- **`search_events`** tool: hybrid retrieval — optional `query` (embedded server-side, cosine via
  pgvector) combined with structured filters: `category`/`subcategory` (enum **generated from the
  canonical taxonomy table**), `date_from`/`date_to`, `neighborhood`, `venue`, `family_friendly`,
  `outdoor`, `free_entry`, `max_price_cents`, `limit ≤ 20`. Returns compact rows.
- **`get_event_details`** tool: full record by event id (description, URL, price, coordinates).
- Delete the hand-rolled keyword/genre tables in `chat/route.ts` (fulfils part of
  `unify-taxonomy` §3.2).
- System prompt: current Berlin date/time (model resolves "tonight" itself), grounding rules
  (recommend only from tool results), and the untrusted-data rule for scraped descriptions.

## Capabilities

### New Capabilities
- `semantic-search` — the two read tools, hybrid retrieval, and the tool-calling chat loop.

### Modified Capabilities
- None. (`event-embeddings` is consumed, not changed. A future `save_event` write tool is
  deferred to the preference-feed's interaction log — see Non-goals.)

## Impact

- **Web (`nachtkarte` repo):** `chat/route.ts` rewritten around the AI SDK tool loop; a query
  endpoint embeds user text via the same OpenRouter gateway; keyword tables deleted.
- **Database:** none beyond `event-embeddings` (reads use the anon key; events are public data —
  RLS posture unchanged).
- **Cost:** per chat turn ≈ one embedding call (fractions of a cent) + the LLM turn itself;
  *lower* than today because compact tool results replace the stuffed event list.
- **Security (OWASP):** LLM01 — event descriptions returned by tools are scraped, untrusted text;
  the system prompt marks tool results as data, and tools never execute anything derived from
  them. No new write path (v1 is read-only).
- **Latency:** +1 embedding round-trip on query turns; offset by smaller prompts.

## Non-goals

- **No LangGraph / agent framework** — a single model↔tools loop; framework follows control flow.
- **No `save_event` in v1** — the bookmark-from-chat write tool lands with the preference-feed
  interaction log (auth + logging exist there); listed as v1.1.
- **No recommendations in chat** — "what should I do?" personalization is the feed's job; chat
  answers questions.
- **No re-ranking model or query rewriting** — plain hybrid retrieval first; measure before adding
  machinery.
