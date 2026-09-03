# Tasks — Staged retrieval with progressive relaxation

Beta-critical workstream 1 (search quality). Raised from the "comedy in Prenzlauer Berg" failure,
2–3 September 2026.

## 0. Prerequisites — this change is wrong to ship before them

- [ ] 0.1 **Neighbourhood is usable as a constraint.** Today the label finds 188 upcoming events in
      Prenzlauer Berg against 2,254 by postcode, and some venues are geocoded ~2 km wrong. Until
      fixed, a stage-1 location constraint fires the ladder for data reasons and every answer
      becomes "nothing there, here's the rest of Berlin".
- [ ] 0.2 **Deduplication before limiting.** 23% of upcoming rows are duplicates and 1,134 groups
      disagree on `subcategory`, so copies of one event can satisfy a sufficiency check.

## 1. Constraint model

- [ ] 1.1 Classify constraints: always-hard (date/time, active explicit price limit, availability,
      legal/access), relaxable (venue, neighbourhood, radius), semantic (free text), ranking signals
      (category, subcategory, genres, title match, popularity)
- [ ] 1.2 Remove the inferred-taxonomy hard gate from `search_events`; subcategory becomes a ranking
      signal. Keep it hard **only** when set by an explicit UI filter
- [ ] 1.3 Constraints are applied inside the ranked query, never as a post-filter on a global top-N

## 2. The ladder

- [ ] 2.1 Deterministic rungs: none → venue → neighbourhood → radius from centroid → city-wide
- [ ] 2.2 One constraint per rung; always-hard constraints are never rungs
- [ ] 2.3 Result metadata: rung, what was relaxed, unrelaxed candidate count
- [ ] 2.4 "Nothing anywhere" is a first-class answer, presented as fact rather than as an empty list

## 3. Sufficiency

- [ ] 3.1 Replace `rows > 0` with "at least k results at or above a similarity floor"
- [ ] 3.2 Calibrate the floor from the golden set with `scripts/eval_retrieval_gate.py`; record it
      with the embedding model id
- [ ] 3.3 The gate fails when the model changes and the floor has not been recalibrated
- [ ] 3.4 Dedup runs before both the limit and the threshold test

## 4. Tracing

- [ ] 4.1 Every attempt traced: arguments as sent, rung, result ids, scores, relaxation reason
- [ ] 4.2 Fix the null tool inputs seen on 2–3 September (related: observability 1.1b)
- [ ] 4.3 A trace alone reproduces the query without database access — asserted, not assumed

## 5. Regression cases, from real failures

- [ ] 5.1 "comedy tonight" — returns comedy including events whose subcategory is NULL
- [ ] 5.2 "comedy in Prenzlauer Berg" — no local results; returns city-wide and says it widened
- [ ] 5.3 duplicate Tati Comedy events collapse to one before limiting
- [ ] 5.4 "hip hop tonight or tomorrow" — untagged taxonomy still retrieved
- [ ] 5.5 a query with no suitable events anywhere — answers honestly, relaxes nothing hard
- [ ] 5.6 wire these into `eval_retrieval_gate.py` as named cases, so a regression fails CI

## 6. Ship

- [ ] 6.1 Baseline the gate before and after; the four currently-empty golden queries should improve
- [ ] 6.2 `/opsx:archive staged-retrieval` + `/opsx:sync`
