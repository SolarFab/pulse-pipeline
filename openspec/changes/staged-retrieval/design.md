# Design — staged retrieval

## What the RPC does today (verified against the live definition)

```
WITH base AS (SELECT e.*, COALESCE(e.neighborhood, v.neighborhood) AS eff_neighborhood, <dist>
              FROM events e LEFT JOIN venues v ON e.venue_id = v.id
              WHERE e.is_active AND start_time BETWEEN … AND (p_subcategory IS NULL OR …) AND …)
SELECT … FROM base WHERE (radius) ORDER BY <title boost>, <embedding <=>>, start_time LIMIT …
```

Constraints already precede ordering and limiting. The defects are the **inferred subcategory gate**
and the **`rows = 0` relaxation trigger**. The RPC returns neither a score nor a dedup key, which is
why sufficiency cannot be built against it as it stands.

## Location: event-first at every tier

Location is **event-first, venue-fallback per tier** — never venue-first. This is not a style
preference; 654 of The Makery's 763 upcoming events carry coordinates that differ from their venue
row, because the organiser roves and the venue row is a stub. Kulturdaten has 2,252 events whose
address differs from the venue's, and Eventbrite has 138 events located with no venue at all. A
postcode lookup that consults `venues` first would relabel every one of them.

| tier | source | resolution |
|---|---|---|
| 1 | postcode | `COALESCE(event_postcode, venue.postal_code)` |
| 2 | district | `COALESCE(event_district, venue.district)` |
| 3 | label | `COALESCE(e.neighborhood, v.neighborhood)` — today's behaviour |
| 4 | radius | centroid distance over `COALESCE(e.lat, v.lat)` |

The first tier producing candidates answers, and the answering tier is returned to the caller.
`events` has no structured postcode column today; until it does, tier 1 reads the venue only for
events with **no event-level address**, and events with their own address fall through to tier 4.

### Event-first requires knowing the coordinate is really the event's

Event-first is only safe when an event's coordinate was genuinely derived from its own address. It
is not, today: when geocoding fails the pipeline **silently falls back to the venue's coordinates**,
and the result is indistinguishable from a real geocode. Two Makery workshops at `Reuterstraße 82,
12053` (Neukölln) are pinned at the organiser's Prenzlauer Berg studio, 6 km away, because their
source addresses were malformed. Eight of Makery's fifteen mis-pins sit on exactly that HQ
coordinate, and `luma` mis-pins 40% of its located events.

So location resolution consumes a **provenance flag** (`geocoded` / `venue_inherited` / `absent`),
and a `venue_inherited` coordinate is treated as the venue's for tier purposes, not the event's.
Without the flag, event-first confidently returns the organiser's HQ. **Blocked on FEAT-26.**

### Area parameter contract

The RPC takes `p_area_id` — a **canonical identifier** from a checked-in `areas` table
(`area_id`, `name`, `aliases[]`, `postcodes[]`, `district`, `centroid_lat/lng`). The orchestrator
resolves a user's words to an `area_id` before calling; **raw model strings never reach SQL**.

**Ownership.** The RPC never sees raw words, so it cannot detect that a phrase matched several
aliases. Layering is therefore:

- **FEAT-25 (web) owns alias resolution.** Words → `area_id`. It emits `area_ambiguous` when a
  phrase matches several areas and asks the user which was meant.
- **FEAT-24 (this change) owns canonical-ID validation only.** An `area_id` absent from the `areas`
  table returns `area_unknown` and applies no area constraint, rather than silently filtering to
  nothing.

## Similarity semantics

pgvector's `<=>` is **cosine distance**. The RPC returns `similarity = 1 - (embedding <=> query)`,
range `[-1, 1]` and in practice `[0, 1]` for normalised embeddings. Higher is better.

- No `query_embedding` supplied, or the event has no embedding → `similarity IS NULL`.
- **A null similarity can never satisfy the floor.** For filter-only searches the floor does not
  apply; sufficiency is `k` deduplicated rows and the response records `threshold_not_applicable`.
- An exact title match still carries its true similarity. The title boost changes rank, not score.

## Ranking contract

Taxonomy stops being a filter and becomes a rank tier. Ordering is a **deterministic comparator
chain**, not a weighted sum — weights would need invented constants and would not be testable:

1. exact title match on `p_query_text` (existing behaviour)
2. **taxonomy agreement** with the ranking inputs — `subcategory`, then `category`, then `genres`
   overlap; a NULL field is a non-match, never an exclusion
3. `similarity` descending, NULLs last
4. `dist_km` ascending when an area or radius was requested
5. `start_time` ascending
6. `id` ascending — **the unique tie-break.** Without it the ordering is not total: many events
   share a `start_time`, so "identical input gives identical order" would not be implementable.

Every tier is independently assertable in a test.

### Ranking inputs and filter inputs are separate parameters

Today one set of parameters does both jobs, which is why an inferred guess acts as a hard gate. The
RPC takes two disjoint sets, so neither repository can read the same field two ways:

| purpose | parameters | effect |
|---|---|---|
| ranking (model-inferred) | `p_rank_category`, `p_rank_subcategory`, `p_rank_genres` | comparator tier 2 only; never excludes |
| hard filter (user-selected) | `p_filter_category`, `p_filter_subcategory` | `WHERE` clause; excludes |

The caller sets filter parameters **only** from an explicit UI selection. The legacy
`p_category` / `p_subcategory` / `p_genres` are removed rather than reinterpreted, so a stale caller
fails loudly instead of silently gating.

## Sufficiency and `k`

**`k = 3`.** A concierge answer shows three options; below that the answer reads as thin. It is
stored in the versioned floor record, not hardcoded at a call site, so it moves with calibration.

- Qualify: `similarity >= floor`, **after** deduplication, **excluding** unknown-price rows when the
  user stated a price limit.
- `count >= k` → answer. `count < k` → next rung.
- At the final rung with `0 < count < k`, answer with what exists and state that it is fewer than
  usual. Returning three weak results was the original bug; returning one honest result is not.

## Price: qualifying versus alternative

An event with `price_cents IS NULL` **cannot satisfy "under €15"** — the system does not know that
it does. The RPC returns `price_qualifies` (boolean) and `price_unknown` (boolean).

- Only `price_qualifies` rows count toward `k`.
- `price_unknown` rows may be returned as clearly labelled alternatives.
- The answer never asserts an unknown price is under the stated limit.

This is stricter than today's RPC, which admits unknown-price rows silently under
`p_max_price_cents`. That silent admission is how unknown values could manufacture sufficiency.

## Deduplication: owned by FEAT-23

FEAT-23 owns the dedup key, its normalisation rules and the SQL collapse. FEAT-24 **consumes** it
and does not reimplement it. The contract FEAT-24 depends on:

- a stable `dedup_key` on every returned row
- duplicates collapsed **before** `LIMIT`
- deterministic winner selection, so the same input yields the same survivor

Normalisation, null handling, start-time tolerance and winner rules are specified in FEAT-23.

## Calibration source

The production floor is calibrated **from the fresh dated fixture only**. The July–August golden set
cannot validate "tonight" and is kept solely as a frozen algorithm-regression suite over a pinned
window. Using it for the shipping floor is the contradiction the second review caught.

### Where the floor record lives, and how the web half reads it

A database table, not checked-in config — FEAT-25 runs in a separate repository and deploys on its
own cadence, so a file would drift from the deployed RPC.

```
retrieval_config(
  id, active boolean, floor real, k int,
  embedding_model text, embedding_dim int,
  fixture_id text, fixture_captured_at date, calibrated_at timestamptz)
```

- **Exactly one active row**, enforced by a partial unique index on `active WHERE active`.
- **Read:** a single `SELECT … WHERE active` — one row, one statement, so a reader can never observe
  a half-applied change. Readable by the anonymous role; writable only by the service role.
- **Write:** a transaction that clears the current active row and inserts the replacement, so
  calibration is atomic rather than a window with no active row.
- **Fail closed:** FEAT-25 compares the row's `embedding_model` and `embedding_dim` against its
  configured model. On mismatch, or no active row, it runs unrelaxed and reports uncalibrated.

### Fixture freshness

`fixture_captured_at` must be within **`FIXTURE_MAX_AGE_DAYS`, default 14**, of the run date, in
`Europe/Berlin`. Boundary: exactly 14 days passes; 15 fails. The check is on the fixture's capture
date, not its file mtime, so re-saving a stale fixture does not refresh it.

## Public-RPC performance and safety

`match_events` is reachable from the anonymous search path, and this change adds a join, an area
lookup, deduplication and vector ordering to it.

Two separate measurements — one plan cannot establish a percentile:

- **Plan evidence:** `EXPLAIN (ANALYZE, BUFFERS)` on three representative queries — tonight
  city-wide, tonight within an area, and a 14-day filter-only window — recorded in the PR. Asserts
  index use and absence of sequential scans on `events`.
- **Latency evidence:** a repeated benchmark, **200 runs per query, warm cache, against production
  catalogue volume**, reporting p50/p95. **p95 under 400 ms.** Cold-cache numbers are recorded for
  information but do not gate, since the anonymous path is served warm.

Indexes required: `events(start_time) WHERE is_active`, `venues(postal_code)`, the existing vector
index, and the dedup key
- limit stays bounded — `least(greatest(p_limit, 1), 20)`
- the function is `STABLE` with `SET search_path = public, pg_temp`, so a mutable `search_path`
  cannot redirect it

## Tracing, and what must never enter a trace

Per attempt: rung, answering location tier, `area_id`, result ids, similarities, relaxation reason,
model and config version, catalogue timestamp. This supports **diagnosis of routing**, not replay —
results depend on mutable catalogue contents.

"Arguments as sent" is deliberately **not** literal. Traces are a second data store, and under
AGENTS.md rule 4 person-level data stays internal and deletable; free-text queries are person-level.

**Allowlisted, recorded verbatim:** the structured arguments — dates, `area_id`, facet booleans,
price limit, ranking and filter taxonomy parameters, limit, rung, model and config version.

**Recorded transformed:** the user's free text as a **SHA-256 hash with a rotating salt**, plus its
length and detected language. Two attempts in one session are comparable; the text is not
recoverable. Full text is recorded only in development, gated on an explicit env flag that is
absent in production.

**Never recorded:** scraped event descriptions (they may carry injected instructions, AGENTS.md
rule 2, and bloat every span), API keys, tokens, embedding vectors, user identifiers beyond an
opaque session id.

**Retention:** traces expire after 30 days. A deletion request removes the session's spans by
opaque session id, so the trace store honours account deletion like every other store.
