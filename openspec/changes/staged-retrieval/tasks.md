# Tasks — Staged retrieval (FEAT-24, pipeline half)

Beta-critical workstream 1. Web half is FEAT-25 in `SolarFab/nachtkarte`.
Revised twice: after the first review (ten findings) and the second (nine).

## 0. Prerequisites — linked, with measurable exits

- [ ] 0.1 **FEAT-22 venue location propagation.** Exit: postcode and district resolvable per event,
      **event-first**; "Prenzlauer Berg" reaches the 2,340 upcoming events its 144 venues host.
- [ ] 0.2 **FEAT-23 deduplication — owns the key, the normalisation and the SQL collapse.**
      Exit: `match_events` returns a stable `dedup_key`, duplicates collapse before `LIMIT`, winner
      selection is deterministic, and a nightly gauge asserts the duplicate rate.
      **FEAT-24 consumes this and does not reimplement it.**

## 1. RPC contract (`event-map`)

- [ ] 1.1 Return `similarity = 1 - (embedding <=> query)`; NULL when either embedding is absent
- [ ] 1.2 Return `price_qualifies` and `price_unknown`; unknown price no longer silently satisfies
      `p_max_price_cents`
- [ ] 1.3 Consume FEAT-23's `dedup_key`; assert collapse happens before `LIMIT`
- [ ] 1.4 Ordering comparator chain: title match → taxonomy agreement → similarity desc NULLs last
      → distance → `start_time`. Each tier separately tested; ordering total and stable
- [ ] 1.5 Drop the inferred-taxonomy hard filter; keep it hard only when flagged as user-selected
- [ ] 1.6 `areas` table (`area_id`, `name`, `aliases[]`, `postcodes[]`, `district`, centroid) and
      `p_area_id` parameter; no raw strings as identifiers
- [ ] 1.7 Location resolution event-first per tier: postcode → district → label → radius; return the
      answering tier. **Regression: The Makery's 654 event-located rows keep their own location**
- [ ] 1.8 Return `area_unknown` / `area_ambiguous` reason codes rather than silently filtering

## 2. Performance and safety (`event-map`)

- [ ] 2.1 `EXPLAIN (ANALYZE, BUFFERS)` on representative windows, recorded in the PR; p95 < 400 ms
- [ ] 2.2 Indexes: `events(start_time) WHERE is_active`, `venues(postal_code)`, dedup key
- [ ] 2.3 `SET search_path = public, pg_temp` on the function; test that it is fixed
- [ ] 2.4 Limit stays bounded at 20

## 3. Calibration (`event-map`)

- [ ] 3.1 Build the **dated scenario fixture** with recorded capture date — the only source for the
      production floor and `k`
- [ ] 3.2 Calibrate the floor and `k` (starting point `k = 3`) from that fixture
- [ ] 3.3 Persist model id, dimension, fixture id, fixture capture date, calibration date, floor, `k`
- [ ] 3.4 Fail closed on mismatch — run unrelaxed, report uncalibrated; asserted in a test
- [ ] 3.5 Keep the July–August qrels as a **frozen algorithm-regression** suite only; assert in CI
      that it does not gate product behaviour

## 4. Evaluation (`event-map`)

- [ ] 4.1 Fixture freshness asserted; a stale fixture fails rather than passing quietly
- [ ] 4.2 Regression cases: comedy tonight · comedy in Prenzlauer Berg with only city-wide
      alternatives · duplicate Tati events · hip-hop with missing taxonomy · nothing suitable
      anywhere · embedding-model change invalidates the floor · unknown-price cannot satisfy a
      stated limit · The Makery event-location precedence

## 5. Handoff to FEAT-25 (`nachtkarte`)

- [ ] 5.1 Publish the contract: `similarity`, `dedup_key`, answering location tier, `area_id`,
      `price_qualifies` / `price_unknown`, reason codes
- [ ] 5.2 Confirm the web half consumes scores rather than re-querying

## 6. Ship

- [ ] 6.1 Frozen gate baselined before and after; ranking maths must not regress
- [ ] 6.2 `/opsx:archive staged-retrieval` + `/opsx:sync`
