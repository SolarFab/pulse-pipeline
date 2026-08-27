# Tasks — Scrape failure reporting (FEAT-9, issue #6, PR #7)
- [x] 1.1 `ScrapeOutcome` dataclass in `scrapers/base.py`; `run()` returns it, crash path sets `error`
- [x] 1.2 `run_all()` counts failed sources, returns their names, keeps running the rest
- [x] 1.3 Summary line reports upserted / rejected rows / failed sources as three numbers
- [x] 1.4 `os._exit(1 if failed_sources else 0)` — verdict carried, hard exit preserved
- [x] 1.5 `run_single()` and `pipeline/scheduler.py` updated to the new shape
- [x] 2.1 `deploy/run-scrape.sh`: fourth verdict `degraded`; all five branches tested on synthetic logs
- [x] 2.2 Fourth/fifth verdict split: zero events + failed sources is `error`, not `empty`
- [x] 2.3 Verdict extracted to `deploy/classify-run.sh` so it is testable at all — inline it was
      verified only by throwaway scripts, the same "checked once, never again" gap FEAT-9 closes
- [x] 2.4 `tests/test_run_verdict.py`: the six-case matrix + edge cases, run against the REAL
      script rather than a Python reimplementation. Mutation-checked: breaking the regex fails 5/9
- [x] 3.1 Nine tests asserting on the COUNT, not on log text (the failures were always logged)
- [x] 3.2 Autouse fixture stubs the geocoder — every test here calls run_all, which would
      otherwise hit Nominatim 1500x and write to production (invisible while the net was dead code)
- [x] 3.3 Tests that the safety net still runs, incl. when sources failed, and is skipped on DRY_RUN
- [ ] 4.1 VERIFY on the 02:00 UTC Hetzner run: `venue_website` and `instagram` appear as failed
- [ ] 5.1 `/opsx:archive scrape-failure-reporting` + `/opsx:sync` once verified
