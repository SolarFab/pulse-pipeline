# Scrape failure reporting

## Why
A source that fails and a source that finds nothing are the same value today. `BaseScraper.run()`
returns `(0, 0)` when `scrape()` raises, `run_all()` catches per-scraper crashes without
incrementing any counter, and the process ends in `os._exit(0)` — so no layer above can tell a
broken night from a quiet one.

This is not a latent risk. `venue_website` (27 venues) and `instagram` (67 venues) have produced
**zero rows in `events` since the project began** — 94 of 139 curated venues — and every run
reported success. `deploy/run-scrape.sh` was built on the principle that an exit code is not
evidence that work happened, then made to read a number that cannot count failures.

With a real-user test in ~10 days, a source breaking silently is the failure we would least like
to hear about from a user.

## What Changes
- `BaseScraper.run()` returns a `ScrapeOutcome` instead of `(success, fail)`. The type exists to
  make emptiness and failure different values: `upserted=0, error=None` is a quiet night,
  `upserted=0, error="..."` is a broken source.
- `run_all()` returns the names of the sources that failed; the summary line reports failed
  **sources** separately from rows rejected during upsert.
- `os._exit` stays — lingering non-daemon threads from the playwright and scheduler imports kept
  the process alive until CI killed it — but it carries the verdict instead of always 0.
- `deploy/run-scrape.sh` gains a fourth verdict, `degraded`: events arrived, so the run is not
  broken, but a source is down.

## Capabilities
### Modified Capabilities
- `pipeline-observability` — a run's outcome becomes countable and its verdict truthful.

## Impact
`scrapers/base.py`, `main.py`, `pipeline/scheduler.py`, `deploy/run-scrape.sh`. No behaviour change
for a healthy run: the same events are scraped and upserted. The observable difference is that a
failing source is now reported and the process exits non-zero.

Callers of `run()` change shape (three call sites, all in this repo).

## Non-goals
Per-source thresholds, day-over-day drop detection, and alert routing. This change makes failure
*countable*; deciding what to do about the count is a separate ticket. Repairing
`venue_website`/`instagram` themselves is also separate — this change only makes them visibly
broken instead of invisibly empty.
