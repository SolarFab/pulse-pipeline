# Tasks — Quality Gates
- [ ] 1.1 [pipeline] Price sanity validator in normalizer + tests (incl. the 86.41 case)
- [ ] 1.2 [pipeline] Time plausibility validator + tests
- [ ] 1.3 [pipeline] Neighborhood-from-PLZ map + ingest derivation + backfill script
- [ ] 2.1 [pipeline] scripts/quality_report.py: gauges + thresholds + markdown artifact
- [ ] 2.2 [ci] Nightly workflow step runs the report; crossing a threshold fails the job
- [ ] 3.1 [db] venue_aliases migration
- [ ] 3.2 [pipeline] Dedup script (exact/near-name, coords-keeper, relink) — dry-run first
- [ ] 3.3 [pipeline] get_venues_by_names consults aliases
