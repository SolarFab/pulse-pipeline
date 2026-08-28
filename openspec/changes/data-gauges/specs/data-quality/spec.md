# data-quality

## ADDED Requirements

### Requirement: The catalogue is asserted after every nightly run
A read-only report SHALL evaluate a fixed set of gauges against the database after the scrape and
record the outcome per gauge as healthy, warning, critical or unknown.

#### SC-DG-01: Report follows the run
- **WHEN** the nightly scrape finishes, whatever its verdict
- **THEN** the gauges are evaluated and their results recorded

#### SC-DG-02: Missing data is not health
- **WHEN** a gauge cannot be evaluated
- **THEN** it is recorded as unknown, never as healthy

### Requirement: Gauges cover the failure modes already observed
The initial set SHALL include source freshness, source volume, upcoming inventory, map visibility,
venue linking, coordinate concentration, taxonomy coverage and embedding coverage. Each SHALL be
able to detect at least one defect this project has actually shipped.

#### SC-DG-03: A source stops producing
- **WHEN** a source produces nothing for two consecutive expected runs
- **THEN** it is critical — this is the `venue_website` / `instagram` case

#### SC-DG-04: A source silently under-collects
- **WHEN** a source's volume falls below its configured floor
- **THEN** it is a warning — this is the `rausgegangen` case

#### SC-DG-05: Events become invisible
- **WHEN** the share of upcoming events without a resolvable coordinate exceeds its threshold
- **THEN** it is critical — this is the `match_events` venue-join case

#### SC-DG-06: Coordinates collapse onto one point
- **WHEN** one coordinate carries events from more than two distinct neighborhoods
- **THEN** it is a warning — this is The Makery case

#### SC-DG-07: The catalogue stops growing
- **WHEN** no new events were created for two consecutive days
- **THEN** it is critical — this is the frozen-catalogue case

### Requirement: Thresholds are explicit and versioned
Each gauge's thresholds SHALL live in version control, per source where sources differ. Thresholds
SHALL NOT be derived from a rolling window of recent history.

#### SC-DG-08: A fix does not read as an anomaly
- **WHEN** a repaired source produces several times its previous volume
- **THEN** no alert is raised for the increase

#### SC-DG-09: Changing a threshold is a reviewable act
- **WHEN** a threshold changes
- **THEN** the change appears in version control with its reason

### Requirement: Severity escalates through the run's own channel
Gauge results SHALL reach the operator by the same path as a failed run, so there is one place to
watch.

#### SC-DG-10: Critical escalates
- **WHEN** any gauge is critical
- **THEN** an alert is delivered naming the gauge and its measured value

#### SC-DG-11: Healthy is quiet
- **WHEN** every gauge is healthy
- **THEN** nothing is delivered
