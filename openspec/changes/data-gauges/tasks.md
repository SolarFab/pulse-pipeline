# Tasks — Nightly data gauges (issue #11)
- [ ] 0.1 Reconcile with the existing `quality-gates` change — one of them owns this
- [ ] 1.1 Gauge module: each gauge is a named SQL query + threshold, returning a status
- [ ] 1.2 Thresholds file, per source, with a comment per number explaining its origin
- [ ] 2.1 Wire into `deploy/run-scrape.sh` after the scrape, before the verdict
- [ ] 2.2 Combine gauge severity with the run verdict into one message
- [ ] 3.1 Backdate-test each gauge against the incident it should have caught:
      rausgegangen pre-fix, Makery pre-backfill, match_events pre-migration, the 16-20 Aug freeze
- [ ] 3.2 SC-DG-08: confirm the post-fix rausgegangen volume raises nothing
- [ ] 4.1 Run for a week reporting only, before anything escalates — a noisy gauge is worse than none
