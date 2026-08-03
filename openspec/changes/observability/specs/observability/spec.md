# observability

## ADDED Requirements

### Requirement: Every concierge turn is traced
When Langfuse is configured, each chat turn SHALL emit one trace with spans for model calls
and tool executions (args summary, result count, ms) plus tokens and cost; tracing failures
SHALL never affect the user response (fire-and-forget).

#### Scenario: Keys absent
- **WHEN** LANGFUSE keys are not configured
- **THEN** the route behaves identically with tracing as a no-op

#### Scenario: Bad answer forensics
- **WHEN** a user reports a wrong answer
- **THEN** its trace shows the exact tool calls, filters and result counts that produced it

### Requirement: Eval and scout runs share the project
Judge/benchmark scripts and the scout SHALL emit traces to the same Langfuse project, tagged
by component, so cost and latency are comparable across the whole system.

#### Scenario: Cost review
- **WHEN** reviewing a week in Langfuse
- **THEN** concierge, scout and eval spend are distinguishable by tag and summable
