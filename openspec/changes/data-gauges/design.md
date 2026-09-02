## Context

The nightly Hetzner run already classifies its outcome and optionally posts one webhook. It does not
inspect whether the resulting catalogue is fresh, visible, linked, embedded, or geographically
plausible. An older `quality-gates` change combines this concern with ingest validation and venue
deduplication; only its nightly-report slice overlaps this change.

The report reads production data with server-side credentials on the batch host. It must remain
read-only and must not become a second scheduler or notification system. FEAT-14 owns delivery of
the combined verdict and must land before gauge alerts can reach a human.

## Goals / Non-Goals

**Goals:**

- Produce one deterministic, machine-readable report after every nightly attempt.
- Encode thresholds in version control with evidence for each number.
- Fold the highest gauge severity into the existing run verdict and webhook payload.
- Preserve `unknown` as a first-class result when a gauge cannot be evaluated.

**Non-Goals:**

- Historical dashboards, automatic repair, ingest-time field validation, or venue deduplication.
- Rolling/anomaly baselines trained on potentially broken history.
- A second alert channel.

## Decisions

### 1. This change exclusively owns nightly catalogue gauges

Remove task 2.1/2.2 and the nightly-gauge requirement from `quality-gates`; that change continues to
own ingest validation and venue deduplication. `data-gauges` becomes the only implementation owner
for nightly catalogue assertions. This avoids two scripts, two threshold formats, and conflicting
failure semantics.

### 2. A Python report emits JSON to stdout and a dated artifact

Implement a module under `pipeline/quality/` with one pure evaluator per gauge and a thin database
reader. A CLI writes a versioned JSON contract containing run timestamp, gauge name, measured
value, threshold, status (`healthy`, `warning`, `critical`, `unknown`), and a short explanation.
`deploy/run-scrape.sh` stores the same output beside the scrape log.

The shell wrapper consumes only the report's documented summary fields. SQL and threshold logic
remain in Python, where they are testable.

### 3. Thresholds are explicit configuration, not code or recent history

Store reviewed YAML/JSON under `config/`, including a rationale and effective date for every global
or per-source floor. Two consecutive missed expected runs is represented using current database
facts plus the source's expected cadence, not mutable process memory.

No upper-volume alarm is added: the repaired `rausgegangen` case proves that increases can be the
healthy transition.

### 4. Severity composition is monotonic

The combined verdict is the worse of scrape and gauge outcomes:

- any `critical` gauge makes an otherwise successful run `degraded`;
- `warning` keeps the run successful but is recorded during the calibration period;
- `unknown` is reported explicitly and becomes `degraded` when it affects a load-bearing gauge;
- a scrape `error`, `empty`, or `timeout` is never downgraded by healthy gauges.

Healthy-only runs remain quiet. One webhook payload carries both scrape summary and non-healthy
gauges, preventing duplicate alerts.

### 5. One-week report-only calibration precedes escalation

For seven completed nightly runs, persist and inspect results without letting gauges change the
outbound verdict. Afterwards enable escalation with a single configuration flag and a recorded
threshold review.

### 6. No ADR

The design extends the existing nightly verdict and alerting boundary. It does not introduce a new
service or architectural dependency.

## Risks / Trade-offs

- **Production queries become expensive** → Use bounded aggregate queries, inspect plans, and avoid
  fetching event rows into Python.
- **Bad thresholds create alert fatigue** → Require evidence comments and the report-only period.
- **Gauge execution fails** → Emit `unknown`; never report healthy and never hide the scrape's own
  verdict.
- **Two changes retain overlapping ownership** → Remove the old nightly tasks/spec delta before
  implementation begins.
- **Alerting is not yet connected** → Complete FEAT-14 first; until then reports are durable but not
  operational alerts.

## Migration Plan

1. Reconcile `quality-gates` so this change is the sole gauge owner.
2. Implement and backdate-test pure evaluators against each named incident.
3. Deploy read-only reporting and retain seven completed runs.
4. Review thresholds, then enable severity composition and FEAT-14 delivery.

Rollback disables escalation while retaining report generation and artifacts. It must not silently
map failed evaluation to healthy.

## Open Questions

None. Initial numeric floors are implementation data derived during the report-only calibration,
not an architectural decision.
