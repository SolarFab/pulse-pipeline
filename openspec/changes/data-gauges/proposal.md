# Nightly data gauges

## Why
Every serious defect this month was in the data, not the code. Each passed lint, types and tests,
and each stayed hidden for weeks or months:

| Defect | Undetected for |
|---|---|
| `rausgegangen` fetched 4 of 12 categories | months |
| The Makery: 722 events on one map pin | months |
| `match_events` missing the venue join — 58% of events invisible to the concierge | months |
| `venue_website` + `instagram` produced zero rows | since the project began |
| Catalogue frozen when Actions minutes ran out | 4 days |

Tests verify code. Nothing verifies that the catalogue is still complete, fresh and visible. Pulse
is a data product, so this is not the last layer of a test pyramid — it is the load-bearing one.

Who benefits: users, who otherwise ask for comedy on a night the catalogue has none because a
scraper quietly stopped fetching that category.

## What Changes
- A read-only report runs after the nightly scrape and evaluates a fixed set of assertions
- Each gauge has an explicit floor per source, not a rolling baseline
- Crossing a threshold escalates through the same channel as a failed run

## Capabilities
### New Capabilities
- `data-quality` — continuous assertions about the catalogue itself.

## Impact
A new script invoked by `deploy/run-scrape.sh` after the run, plus thresholds in version control.
Read-only against the database.

## Why not a rolling baseline
The obvious design — warn when a source drops more than 50% below its recent median — is wrong
here, because the history contains the broken period. `rausgegangen` produced ~143 events per
three days for months while fetching a third of its categories; after the fix, one run produced
1,073. A 7-day median would have flagged the repaired state as the anomaly and the broken state as
normal.

Thresholds are therefore explicit, in version control, and revised deliberately when a fix changes
what normal means.

## Dependencies
Delivery depends on `run-alerting`. A gauge that only writes a log repeats the failure it exists
to catch.

Overlaps the existing `quality-gates` change — reconcile rather than duplicate.

## Non-goals
Dashboards, historical charts, per-venue quality scores, automatic repair. Detection only.
