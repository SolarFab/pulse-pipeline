# Design — staged retrieval

## What the RPC does today (verified, not assumed)

`match_events` is a single SQL statement:

```
WITH base AS (SELECT e.*, COALESCE(e.neighborhood, v.neighborhood) AS eff_neighborhood, <dist>
              FROM events e LEFT JOIN venues v ON e.venue_id = v.id
              WHERE e.is_active AND start_time BETWEEN p_date_from AND p_date_to
                AND (p_subcategory IS NULL OR e.subcategory = p_subcategory)
                AND (p_neighborhood IS NULL OR eff_neighborhood ILIKE '%…%') AND …)
SELECT … FROM base WHERE (radius) ORDER BY <title boost>, <embedding <=>>, start_time LIMIT …
```

Constraints are already applied before ordering and limiting. The defects are the **inferred
subcategory gate** and the **`rows = 0` relaxation trigger**, not the shape of the query.

It returns no similarity score and no dedup key, which is why sufficiency and deduplication cannot
be implemented against it as it stands.

## Location resolution

Ordered, most authoritative first. The first source that yields a non-empty candidate set wins, and
the rung records which one answered:

1. `venues.postal_code` mapped from the requested area name (2,392 of 3,325 venues)
2. `venues.district` (1,084)
3. `COALESCE(e.neighborhood, v.neighborhood)` — today's behaviour, kept as fallback
4. radius from the area centroid over `COALESCE(e.lat, v.lat)` (coordinates: 3,325 of 3,325)

An area name resolves to a postcode set through a checked-in table, not a model guess. Coordinates
are complete but not always accurate — some venues carry rounded values placing them in the wrong
Ortsteil — so radius is the fallback, never the primary source.

## Hard-constraint semantics, stated because they were undefined

| constraint | field | rule |
|---|---|---|
| date/time | `start_time` within window | always hard |
| availability | `is_active` | always hard; there is no ticket-inventory field, so "availability" means active, nothing more |
| explicit price limit | `price_cents` | hard **only** when the user states a figure |
| unknown price | `price_cents IS NULL` | **eligible today** — the RPC admits it. Kept, and the row is labelled price-unknown so the model can say so |
| access | — | **no supporting field exists.** Removed from the always-hard set rather than specified against nothing |

The unknown-price rule is a deliberate product decision, not an accident: excluding unknown-price
events would hide most of the catalogue. It must be visible in the answer, not silent.

## The ladder

Deterministic, in application code, one rung per attempt. The model never decides to widen; it
receives results plus metadata and verbalises the outcome.

| rung | relax | keep |
|---|---|---|
| 0 | nothing | — |
| 1 | venue | area, semantics, hard set |
| 2 | area → radius from centroid | semantics, hard set |
| 3 | radius → city-wide | semantics, hard set |
| 4 | stop — answer that there is nothing | — |

Hard constraints are immutable inputs shared by every rung, constructed once before rung 0.

## Sufficiency

At least `k` results at or above a similarity floor, measured **after** deduplication. `rows > 0` is
what produced the 3 September failure.

The floor is stored as a versioned record: embedding model id, embedding dimension, evaluator
fixture id and its freshness date, the calibration date, and the value. **A mismatch fails closed** —
the search runs unrelaxed and reports that the floor is uncalibrated, rather than silently reusing
a number calibrated against a different model.

## Evaluation: two suites, different jobs

The existing golden set covers events from 30 July – 2 August, all now in the past. It cannot
validate "tonight" and must not gate shipping behaviour.

- **Frozen algorithm regression** — the existing qrels via `scripts/eval_retrieval_gate.py`, over a
  pinned historical window. Answers "did the ranking maths change".
- **Dated scenario fixture** — a small, fresh snapshot with recorded capture date, covering the six
  real-failure cases. Answers "does the product behave". Its freshness is asserted; a stale fixture
  fails the suite rather than passing quietly.

## Tracing

Every attempt, not only the last: arguments as sent, rung, which location source answered, result
ids, similarity scores, relaxation reason, model and config version, and the catalogue timestamp.

This supports **diagnosis**, not replay. Results depend on mutable database contents, so a trace
cannot reproduce a result set exactly without a data snapshot. The requirement is that a trace alone
explains *why the router behaved as it did* — which rung fired and on what evidence.
