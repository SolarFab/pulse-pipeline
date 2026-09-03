# Tasks — Staged retrieval (FEAT-24, pipeline half)

Beta-critical workstream 1. Web half is FEAT-25 in `SolarFab/nachtkarte`.
Revised 2026-09-03 after spec and architecture review returned it to phase 2.

## 0. Prerequisites — linked, with measurable exits

- [ ] 0.1 **FEAT-22 venue location propagation.** Exit: a named area resolves through
      `venues.postal_code` / `district`; "Prenzlauer Berg" reaches the 2,340 upcoming events its
      144 venues host, against 188 by the current label.
- [ ] 0.2 **FEAT-23 deduplication.** Exit: `match_events` emits a stable dedup key and collapses
      duplicates before `LIMIT`; the 23% duplicate rate is asserted by a nightly gauge.

## 1. RPC contract (`event-map`)

- [ ] 1.1 Return `similarity` per row when an embedding is supplied
- [ ] 1.2 Return a stable `dedup_key` (normalised title + venue + start)
- [ ] 1.3 Collapse duplicates before `LIMIT`, keeping the best-tagged copy deterministically
- [ ] 1.4 Location resolution: postcode → district → neighbourhood label → centroid radius, with
      the answering source returned to the caller
- [ ] 1.5 Checked-in area→postcode mapping for Berlin; no model-supplied area strings reach SQL
- [ ] 1.6 Keep unknown-price rows eligible under a price limit and flag them `price_unknown`
- [ ] 1.7 Migration + tests: dedup before limit, similarity present, each location source exercised

## 2. Threshold calibration (`event-map`)

- [ ] 2.1 Sweep the floor over the frozen golden set with `scripts/eval_retrieval_gate.py`
- [ ] 2.2 Persist the floor with embedding model id, dimension, fixture id, fixture freshness date,
      calibration date
- [ ] 2.3 Fail closed on mismatch — run unrelaxed and report uncalibrated; assert this in a test

## 3. Evaluation suites (`event-map`)

- [ ] 3.1 Keep the existing qrels as a **frozen algorithm-regression** suite over a pinned window;
      it does not gate product behaviour
- [ ] 3.2 New **dated scenario fixture** with recorded capture date for product behaviour
- [ ] 3.3 Fixture freshness asserted; a stale fixture fails rather than passing quietly
- [ ] 3.4 Regression cases: comedy tonight · comedy in Prenzlauer Berg with only city-wide
      alternatives · duplicate Tati events · hip-hop with missing taxonomy · nothing suitable
      anywhere · embedding-model change invalidates the floor

## 4. Handoff to FEAT-25 (`nachtkarte`)

- [ ] 4.1 Publish the RPC contract — similarity, dedup key, location source, price-unknown flag
- [ ] 4.2 Confirm the web half consumes scores rather than re-querying

## 5. Ship

- [ ] 5.1 Baseline the frozen gate before and after; ranking maths must not regress
- [ ] 5.2 `/opsx:archive staged-retrieval` + `/opsx:sync`
