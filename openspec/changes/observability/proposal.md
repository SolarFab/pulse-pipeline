# Observability — Langfuse

## Why
Chat, scout and evals each log locally; nothing correlates a user's bad answer with its tool
calls, latency and cost — and Finding 13's defects were invisible for days. One tracing plane
across TS (concierge) and Python (scout, judges) closes that.

## What Changes
- **Langfuse** (cloud EU first; self-host documented) as the single tracing backend:
  concierge turns (model, tools, args summary, result counts, latency, tokens, cost),
  stage-2/judge runs, and the scout (per-node spans) — all one project, all optional-guarded
  (no keys → no-op).
- Keep prompts in versioned files (no Langfuse prompt management); keep scout_runs/eval JSONs
  as durable product artifacts — Langfuse is the operational lens, not the source of record.

## Capabilities
### New Capabilities
- `observability` — tracing integration + minimal dashboards conventions.

## Impact
web (chat route callback), pipeline (judge/eval scripts), capstone repo (scout callback —
specced there). Zero behavior change; failures in tracing must never affect user paths.

## Non-goals
Metrics/alerting stack (quality-gates owns gauges) · log aggregation · Langfuse prompt/dataset
features (our eval harness owns datasets).
