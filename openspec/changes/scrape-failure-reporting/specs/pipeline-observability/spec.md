# pipeline-observability

## ADDED Requirements

### Requirement: A failed source is distinguishable from an empty one
`BaseScraper.run()` SHALL return an outcome carrying an explicit error state. A source that
completes without finding events SHALL be reported as successful with zero events; a source whose
scrape raises SHALL be reported as failed. The two SHALL NOT share a representation.

#### Scenario: A source has nothing on tonight
- **WHEN** a scraper completes and yields no events
- **THEN** the run reports it as successful with zero events, and it is not counted as a failure

#### Scenario: A source raises
- **WHEN** a scraper's `scrape()` raises an exception
- **THEN** the run reports it as failed, carrying the exception type and message

#### Scenario: A source fails without raising to the caller
- **WHEN** `run()` itself returns an outcome with an error set
- **THEN** the caller counts it as failed, exactly as if it had raised

### Requirement: A run reports how many sources failed
`run_all()` SHALL count failed sources separately from individual events rejected during upsert,
and SHALL surface both in its summary line. One failing source SHALL NOT prevent the remaining
sources from running.

#### Scenario: Mixed run
- **WHEN** one source crashes, one fails internally, and one succeeds
- **THEN** the successful source's events are still upserted, and the summary names both failures

#### Scenario: The summary is machine-readable
- **WHEN** a run finishes
- **THEN** the summary line states upserted events, rejected rows and failed sources as three
  distinct numbers, in a form `deploy/run-scrape.sh` can parse

### Requirement: The exit code carries the verdict
The process SHALL exit non-zero when any source failed. The hard exit that works around lingering
non-daemon threads SHALL be preserved, since removing it caused runs to hang until CI killed them.

#### Scenario: All sources healthy
- **WHEN** every source completes
- **THEN** the process exits 0

#### Scenario: Any source failed
- **WHEN** at least one source failed
- **THEN** the process exits non-zero, and still terminates promptly rather than hanging

### Requirement: The post-scrape safety net runs regardless of failures
After every source has been attempted, `run_all()` SHALL link freshly scraped events to known
venues and geocode a bounded tail of events missing coordinates, before returning. This SHALL
happen whether or not sources failed: the events that did arrive still need coordinates, and an
unlinked event has none and is therefore invisible on the map.

#### Scenario: A healthy run
- **WHEN** every source completes
- **THEN** venue linking and geocoding run before the function returns

#### Scenario: Some sources failed
- **WHEN** one or more sources failed but others produced events
- **THEN** venue linking and geocoding still run

#### Scenario: Dry run
- **WHEN** `DRY_RUN` is set
- **THEN** the safety net is skipped, as nothing may be written

### Requirement: The nightly wrapper reports a degraded run as degraded
`deploy/run-scrape.sh` SHALL classify a run in which events arrived but at least one source failed
as `degraded`, distinct from `ok`. Reporting such a run as `ok` is the failure mode this change
exists to remove.

#### Scenario: Events arrived but a source is down
- **WHEN** the summary reports upserted events and one or more failed sources
- **THEN** the wrapper notifies `degraded`, not `ok`

#### Scenario: Nothing arrived and every source was healthy
- **WHEN** the summary reports zero upserted events and zero failed sources
- **THEN** the wrapper notifies `empty` — a genuinely quiet night

#### Scenario: Nothing arrived because sources failed
- **WHEN** the summary reports zero upserted events and one or more failed sources
- **THEN** the wrapper notifies `error`, not `empty`

A total outage and a quiet night both produce zero events. Reporting them alike would restore, at
the wrapper level, exactly the ambiguity this change removes inside the pipeline.
