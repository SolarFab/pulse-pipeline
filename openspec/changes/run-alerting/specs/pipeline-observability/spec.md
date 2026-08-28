# pipeline-observability

## ADDED Requirements

### Requirement: A non-ok run notifies the operator
When a nightly run ends in `degraded`, `empty`, `error` or `timeout`, a message SHALL reach the
operator without them looking for it.

#### SC-AL-01: A degraded run notifies
- **WHEN** events arrived but at least one source failed
- **THEN** a message is delivered naming the failed sources

#### SC-AL-02: A broken run notifies
- **WHEN** the run produced no events, or did not finish
- **THEN** a message is delivered carrying the tail of the log

#### SC-AL-03: A healthy run is quiet
- **WHEN** a run ends `ok`
- **THEN** no alert is delivered — an alarm that fires nightly is ignored within a week

### Requirement: A run that never happened is detected
Absence SHALL be distinguishable from success. The run cannot report its own non-existence, so the
detection SHALL live outside it.

#### SC-AL-04: No run by the expected time
- **WHEN** no verdict has arrived by a deadline after the scheduled start
- **THEN** an alert is raised

### Requirement: Alerting failure never breaks the run
The scrape SHALL complete and record its verdict locally even when the notification channel is
unreachable.

#### SC-AL-05: Webhook down
- **WHEN** the webhook cannot be reached
- **THEN** the run still finishes, the verdict is still written to the log, and the delivery
  failure is itself visible in that log
