# Tasks — Staged retrieval (FEAT-24, pipeline half)

Beta-critical workstream 1. Web half is FEAT-25 in `SolarFab/nachtkarte`.
Revised twice: after the first review (ten findings) and the second (nine).

## 0. Prerequisites — linked, with measurable exits

- [ ] 0.1 **FEAT-22 venue location propagation.** Exit: postcode and district resolvable per event,
      **event-first**; "Prenzlauer Berg" reaches the 2,340 upcoming events its 144 venues host.
- [ ] 0.2 **FEAT-26 geocode provenance.** Exit: every event carries `geocoded` /
      `venue_inherited` / `absent`; a failed geocode never inherits silently. Without this,
      event-first resolution returns the organiser's HQ as though it were the event's location.
- [ ] 0.3 **FEAT-23 deduplication — owns the key, the normalisation and the SQL collapse.**
      Exit: `match_events` returns a stable `dedup_key`, duplicates collapse before `LIMIT`, winner
      selection is deterministic, and a nightly gauge asserts the duplicate rate.
      **FEAT-24 consumes this and does not reimplement it.**

## 1. RPC contract (`event-map`)

- [ ] 1.1 Return `similarity = 1 - (embedding <=> query)`; NULL when either embedding is absent
- [ ] 1.2 Return `price_qualifies` and `price_unknown`; unknown price no longer silently satisfies
      `p_max_price_cents`
- [ ] 1.3 Consume FEAT-23's `dedup_key`; assert collapse happens before `LIMIT`
- [ ] 1.4 Ordering comparator chain: title match → taxonomy agreement → similarity desc NULLs last
      → distance → `start_time` → **`id`**. The `id` tier makes the ordering total; each tier
      separately tested, including two events sharing a `start_time`
- [ ] 1.5 Split the taxonomy parameters: `p_rank_category` / `p_rank_subcategory` / `p_rank_genres`
      (order only) and `p_filter_category` / `p_filter_subcategory` (exclude). **Remove** the legacy
      `p_category` / `p_subcategory` / `p_genres` so a stale caller fails loudly
- [ ] 1.6 `areas` table (`area_id`, `name`, `aliases[]`, `postcodes[]`, `district`, centroid) and
      `p_area_id` parameter. **Canonical-ID validation only** — alias resolution and
      `area_ambiguous` belong to FEAT-25, since raw words never reach SQL
- [ ] 1.7 Location resolution event-first per tier: postcode → district → label → radius; return the
      answering tier. A `venue_inherited` coordinate counts as the venue's, not the event's.
      **Regressions:** The Makery's 654 genuinely event-located rows keep their own location, and
      the two Reuterstraße 82 workshops do **not** resolve to Prenzlauer Berg
- [ ] 1.8 An `area_id` absent from `areas` returns `area_unknown` and applies no area constraint,
      rather than silently filtering to nothing

## 2. Performance and safety (`event-map`)

- [ ] 2.1 **Plan evidence:** `EXPLAIN (ANALYZE, BUFFERS)` on three representative queries — tonight
      city-wide, tonight in an area, 14-day filter-only — recorded in the PR; index use shown, no
      sequential scan on `events`
- [ ] 2.2 **Latency evidence, separately:** 200 warm-cache runs per query at production volume,
      reporting p50/p95; **p95 < 400 ms**. Cold-cache recorded for information, does not gate
- [ ] 2.2b Indexes: `events(start_time) WHERE is_active`, `venues(postal_code)`, dedup key
- [ ] 2.3 `SET search_path = public, pg_temp` on the function; test that it is fixed
- [ ] 2.4 Limit stays bounded at 20

## 3. Calibration (`event-map`)

- [ ] 3.1 Build the **dated scenario fixture** with recorded capture date — the only source for the
      production floor and `k`
- [ ] 3.2 Calibrate the floor and `k` (starting point `k = 3`) from that fixture
- [ ] 3.3 `retrieval_config` table — floor, `k`, embedding model, dimension, fixture id, fixture
      capture date, calibration date. Partial unique index enforcing **exactly one active row**;
      anonymous read, service-role write; replacement in a transaction so it is atomic
- [ ] 3.4 Fail closed on model/dimension mismatch **and on no active row** — run unrelaxed, report
      uncalibrated; both asserted in tests
- [ ] 3.5 Keep the July–August qrels as a **frozen algorithm-regression** suite only; assert in CI
      that it does not gate product behaviour

## 4. Evaluation (`event-map`)

- [ ] 4.1 Fixture freshness: `fixture_captured_at` within `FIXTURE_MAX_AGE_DAYS` (default 14),
      evaluated in `Europe/Berlin`, from the recorded capture date not file mtime. Boundary tested
      at exactly 14 (pass) and 15 (fail)
- [ ] 4.2 Regression cases: comedy tonight · comedy in Prenzlauer Berg with only city-wide
      alternatives · duplicate Tati events · hip-hop with missing taxonomy · nothing suitable
      anywhere · embedding-model change invalidates the floor · unknown-price cannot satisfy a
      stated limit · The Makery event-location precedence · a venue-inherited coordinate is not
      treated as an event location

## 4b. Trace privacy (`event-map` defines, FEAT-25 implements)

- [ ] 4b.1 Allowlist of structured arguments recorded verbatim
- [ ] 4b.2 User free text recorded as salted SHA-256 plus length and detected language; verbatim
      capture only behind a development-only flag absent in production
- [ ] 4b.3 Prohibited in spans: scraped descriptions, credentials, embedding vectors, user
      identifiers beyond an opaque session id
- [ ] 4b.4 30-day retention; deletion by session id, so traces honour account deletion
      (AGENTS.md rule 4)

## 5. Handoff to FEAT-25 (`nachtkarte`)

- [ ] 5.1 Publish the contract: `similarity`, `dedup_key`, answering location tier, `area_id`,
      `price_qualifies` / `price_unknown`, `area_unknown`, the rank/filter parameter split, and the
      `retrieval_config` read contract
- [ ] 5.3 FEAT-25 owns alias → `area_id` resolution and `area_ambiguous`
- [ ] 5.2 Confirm the web half consumes scores rather than re-querying

## 6. Ship

- [ ] 6.1 Frozen gate baselined before and after; ranking maths must not regress
- [ ] 6.2 `/opsx:archive staged-retrieval` + `/opsx:sync`
