# Staged retrieval with progressive relaxation

FEAT-24 · beta-critical workstream 1 (search quality)

## Why

On 2 September a user asked for **comedy in Prenzlauer Berg** and was told there was nothing.
On 3 September the same question returned three events while more comedy existed. Both answers
come from two defects in how the concierge decides *when it has found enough*.

**Defect 1 — inferred taxonomy is used as a hard gate.** The model infers `subcategory` from free
text and passes it to `match_events`, which filters on it exactly. Of 97 upcoming comedy events,
**45 carry no subcategory at all**. A hard gate on a 46%-incomplete field hides the catalogue
rather than narrowing it.

**Defect 2 — relaxation triggers on `rows = 0`.** Three weakly-matching rows are treated as
success, so the search never widens even when stronger candidates sit one constraint away. That is
exactly the 3 September answer.

### What this proposal previously got wrong

An earlier revision claimed the system retrieves a global vector top-N and applies constraints
afterwards. **That is false.** `match_events` applies date, taxonomy, neighbourhood, venue, facets
and price inside the `base` CTE, and the radius in the outer `WHERE`, all **before** `ORDER BY` and
`LIMIT`. Constraints already shape the ranked query. The RPC also already resolves location as
`COALESCE(e.neighborhood, v.neighborhood)` — an earlier claim that it reads only the event column
was likewise wrong. Both errors are corrected here; no task depends on them.

## What Changes

Constraints are classified by how hard they really are, and sufficiency becomes a quality test
rather than a row count.

- **Always hard** — date and time window, `is_active`, an explicitly stated price limit, and access
  constraints. Never relaxed.
- **Initially hard, relaxable** — venue, neighbourhood, radius, in that order.
- **Semantic by default** — comedy, romantic, underground, chill. Never a taxonomy gate.
- **Ranking signals** — category, subcategory, genres, title match, popularity. They order results;
  they do not exclude them.
- **Hard taxonomy only on explicit request** — a "Workshops only" UI toggle, never an inferred intent.

A deterministic ladder in **application code** widens one constraint at a time until the result
clears a calibrated relevance floor, then answers honestly about what was widened.

> Tonight I couldn't find comedy in Prenzlauer Berg, but here are three strong options elsewhere.

## Delivery is split across two repositories

Per the delivery contract this is **two cards and two PRs**:

- **`event-map` (this change)** — the RPC contract: return a similarity score and a stable dedup
  key, deduplicate before `LIMIT`, and resolve location from the authoritative source.
- **`nachtkarte` (FEAT-25)** — the relaxation state machine, response metadata, prompt changes and
  Langfuse spans.

`Touches web = Yes`.

## Prerequisites, with measurable exits

- **FEAT-22 · venue location propagation.** `match_events` filters `COALESCE(e.neighborhood,
  v.neighborhood)`, which is a text label of mixed granularity. Structured `postal_code`, `city`
  and `district` now exist on `venues` (postcode on 2,392 of 3,325). Resolution must stay
  **event-first at every tier**: 654 of The Makery's 763 upcoming events carry coordinates that
  differ from their venue row, so a venue-first lookup would relabel them. **Exit:** a named area
  resolves event-first through postcode/district with a radius fallback, and "Prenzlauer Berg"
  reaches the 2,340 upcoming events its 144 venues host rather than the 188 the label finds.
- **FEAT-26 · geocode provenance.** Event-first resolution assumes an event's coordinate is its
  own. When geocoding fails the pipeline silently inherits the venue's, and the two are
  indistinguishable — so event-first would return the organiser's HQ as fact. **Exit:** provenance
  is recorded per event and a failed geocode is `absent`, never a silent inheritance.
- **FEAT-23 · deduplication.** 23% of upcoming rows are duplicates; 1,134 groups disagree on
  `subcategory`. **FEAT-23 owns the key, its normalisation and the SQL collapse**; this change
  consumes them and does not reimplement them. **Exit:** `match_events` returns a stable
  `dedup_key`, duplicates collapse before `LIMIT`, and winner selection is deterministic.

## Non-goals

Learned re-ranking. Changing the map. Multi-turn memory of previous relaxations.
