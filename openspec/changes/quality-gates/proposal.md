# Quality Gates

## Why
Finding 13: one wrong concierge answer decomposed into five silent data defects — none had a
gauge. Ad-hoc fixes (times, venues, linking, comedy) repaired instances; this change installs
the class-level instruments so regressions surface within a day, not when a user complains.

## What Changes
- **Ingest checks** (pipeline, deterministic): price sanity (no "Free – 86.41 EUR" ranges,
  currency plausibility), time plausibility (no 03:00 kids events, end>start, duration <24h),
  neighborhood derivation from PLZ/address when missing.
- **Nightly quality report**: one artifact with the load-bearing gauges — unembedded-upcoming
  count, unlinked-venue count, invisible-on-map count, dead-subcategory usage, taxonomy-audit
  rate (weekly), duplicate-venue candidates, per-source freshness. Fails loudly (issue/log
  annotation) when a gauge crosses its threshold.
- **Venue dedup pass** (one-off + monitor): merge exact-name/near-name duplicates (ANOHA ×2,
  Galli ×2, Punch Line ×2...), keeping the coords-bearing row; alias table for spelling variants.

## Capabilities
### New Capabilities
- `quality-gates` — ingest validations, gauges, nightly report, dedup.

## Impact
Pipeline only (+1 small migration for venue aliases). No user-facing changes except better data.

## Non-goals
LLM-based quality judgment (gauges are deterministic); fixing all flagged items (report
surfaces, humans/audits decide); web UI for the report (markdown/log artifact first).
