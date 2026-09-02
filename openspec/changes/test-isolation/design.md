## Context

Pipeline tests inherit the developer shell and may load `.env`, including a production
`SUPABASE_SERVICE_KEY`. They can also open arbitrary sockets. The FEAT-9 regression demonstrated
that a newly reachable code path can turn a harmless-looking unit test into a slow production
mutation.

This ticket protects the Python repository. Web/Vitest isolation belongs to a separate web card and
PR because `web/` is a separate repository and this card is not marked `Touches web`.

## Goals / Non-Goals

**Goals:**

- Deny sockets before test code can contact Supabase, Nominatim, model providers, or any other host.
- Remove production-capable credentials from the test process before application imports occur.
- Make exceptions local, explicit, and restricted to non-production endpoints.

**Non-Goals:**

- Providing a local Supabase stack or a general integration-test environment.
- Governing Vitest or Playwright in `SolarFab/nachtkarte`.
- Proving that mocked responses accurately model every external service.

## Decisions

### 1. The default test command disables sockets globally

Add `pytest-socket` to the locked development dependencies and configure pytest with
`--disable-socket`. Do not add a suite-wide allow marker. Unit tests mock at the HTTP/client
boundary and fail on the first forgotten connection.

For a genuine integration test, use a registered `integration` marker plus a fixture that calls
`socket_enabled` only for that test after validating its configured URL is localhost or a named
throwaway project. A marker by itself is documentation, not permission.

### 2. Credentials are scrubbed in root `tests/conftest.py`

At session start, remove `SUPABASE_SERVICE_KEY` and other production-capable secrets before test
modules import application code. Preserve only explicitly test-prefixed variables. Tests needing a
client receive it through a fixture with a fake or throwaway URL/key; production host patterns are
rejected.

The environment fence and socket fence are independent. Either one alone is insufficient: a mock
can be removed later, and credentials can be renamed or loaded from another path.

### 3. Shared fixtures replace file-local safety patches

Provide root fixtures for the Supabase client and geocoder boundary. Remove the FEAT-9 file-local
autouse fixture only after the global fence proves that the same tests pass without network access.
Do not autouse-mock every application dependency: the socket fence is the final safety net, while
tests should still select the behavior they replace.

### 4. CI supplies no production secrets

The unit-test job receives no repository production environment and no Supabase service-role
secret. Integration tests, when introduced separately, use a dedicated environment/job with named
non-production credentials.

### 5. No ADR

This is a test-safety mechanism inside an existing boundary, not a lasting production architecture
decision.

## Risks / Trade-offs

- **Libraries use harmless localhost sockets** → Permit only the individual test and only the
  validated local endpoint; never enable sockets for a directory.
- **Import-time clients read secrets before fixtures run** → Scrub environment during conftest
  loading and refactor import-time client construction when surfaced.
- **A test skips instead of proving behavior** → Unit tests must use fakes; skipping is reserved for
  explicitly selected integration tests with missing throwaway configuration.
- **False confidence from network denial alone** → Add a regression test that deliberately attempts
  a connection and asserts immediate failure.

## Migration Plan

1. Add and lock `pytest-socket`; add marker declarations and root safety fixtures.
2. Run the complete suite and repair each newly exposed network dependency individually.
3. Remove the FEAT-9 local safety fixture and rerun its tests.
4. Run a deliberate socket attempt and a production-credential sentinel test.
5. Enable the same default command in CI.

Rollback may remove the plugin/configuration if it blocks all development, but must retain the
credential scrub and document the discovered network callers before doing so.

## Open Questions

None. Web test isolation should be raised as a separate `nachtkarte` card rather than expanding
this pipeline ticket across repositories.
