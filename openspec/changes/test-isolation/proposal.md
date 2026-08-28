# Tests cannot reach production or the network

## Why
Nothing prevents a test from writing to the live database. During FEAT-9 this stopped being
theoretical: repairing an unreachable code path made every test in one file geocode up to 1,500
events against Nominatim and write the results to production. It was noticed only because the run
hung.

While that code was dead the same tests looked harmless. The hazard appeared the moment the bug
was fixed — so "no test has caused damage yet" is not evidence of safety.

The pipeline's `.env` carries `SUPABASE_SERVICE_KEY`, which bypasses RLS entirely (AGENTS.md
rule 1). The only thing between a test and production today is one `autouse` fixture in one file,
written by the same agent that caused the problem.

Who benefits: everyone, but especially the agent-written tests that will arrive faster than anyone
can review each one for a forgotten stub.

## What Changes
- Sockets are denied by default in the test suite; a test that needs one declares it
- The test environment does not carry production credentials
- Tests that legitimately need a real service use an explicit marker and a non-production target

## Capabilities
### New Capabilities
- `test-isolation` — the boundary between the suite and the outside world.

## Impact
`pyproject.toml` (pytest config + dev dependency), `tests/conftest.py`, and any existing test that
quietly used the network — surfacing those is the point.

## Non-goals
Building an integration-test environment, seeding fixtures, local Supabase. This ticket is the
fence, not what runs inside it.

## Security
Directly serves AGENTS.md rule 1: a service-role key must never be on a path that can be triggered
casually. A test run is exactly such a path.
