# test-isolation

## ADDED Requirements

### Requirement: Network access is denied by default
The test suite SHALL block outbound network connections unless a test explicitly opts in. A test
that forgets to stub an external call SHALL fail immediately and visibly, rather than succeeding
slowly against a real service.

#### SC-TI-01: An unstubbed call fails fast
- **WHEN** a test opens a socket without opting in
- **THEN** it fails with an error naming the attempted connection

#### SC-TI-02: Failure is immediate, not a hang
- **WHEN** a test would otherwise make many slow external calls
- **THEN** it fails on the first one rather than running to completion

#### SC-TI-03: Opting in is explicit and local
- **WHEN** a test genuinely requires a network service
- **THEN** it declares that with a marker, and the allowance applies to that test only

### Requirement: The suite has no production credentials
Tests SHALL NOT run with credentials that grant access to the production database.

#### SC-TI-04: Service-role key absent
- **WHEN** the suite runs in CI or locally via `make check`
- **THEN** `SUPABASE_SERVICE_KEY` is not populated with the production value

#### SC-TI-05: A missing credential fails loudly
- **WHEN** a test needs a database and none is configured
- **THEN** it fails or skips with a clear message, and never silently falls back to production

### Requirement: Existing tests are audited, not grandfathered
Enabling the fence SHALL surface tests that currently rely on the network. Each SHALL be either
stubbed or explicitly marked — none SHALL be exempted wholesale.

#### SC-TI-06: No blanket exemption
- **WHEN** the fence is enabled
- **THEN** no directory- or suite-wide opt-out exists; exemptions are per test and justified
