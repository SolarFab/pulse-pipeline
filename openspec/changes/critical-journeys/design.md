## Context

Both journeys exercise the Next.js product in `SolarFab/nachtkarte`; no implementation belongs in
the pipeline repository. The concierge requires a real authenticated user, makes a paid model call,
and resolves cited event IDs. The map is rendered by MapLibre from upcoming events with resolvable
coordinates.

The Berlin user test may change the UI, so selectors and detailed flows must be implemented only
after that test. Architecture can still fix the execution boundary, environments, secrets, cost,
and failure semantics now.

## Goals / Non-Goals

**Goals:**

- Protect two previously broken user-visible chains in an isolated Playwright project.
- Separate a deterministic required browser gate from a paid live concierge canary.
- Use a dedicated account, model key, budget, and preview environment.
- Make absence of suitable catalogue data visible without misdiagnosing it as a UI regression.

**Non-Goals:**

- Broad UI coverage, visual snapshots, login-flow testing, or catalogue-health monitoring.
- Calling live paid services on every pull request.
- Implementing tests in `nachtkarte-pipeline`.

## Decisions

### 1. Move this change to the web repository before development

The OpenSpec artifacts should live in `SolarFab/nachtkarte`, and the Notion card's repository/spec
link must point there. The pipeline PR may retain history, but implementation must not add files
under its ignored `web/` checkout. Because this feature touches only web, it needs one web card/PR,
not two cross-repository cards.

### 2. Split deterministic preview tests from the live model canary

The required Playwright project uses a seeded/controlled preview and intercepts the model boundary
with a deterministic streamed response containing a real seeded event ID. It proves authentication
state, streaming UI, citation resolution, map rendering, and detail navigation without provider
cost or model variance.

A separate scheduled or manually dispatched `live-concierge` project uses the dedicated OpenRouter
key against a deployed preview. It is non-required initially, has one bounded prompt, no retries on
provider failure, a hard timeout, and a monthly provider budget. Its result is operational evidence,
not a deterministic merge gate.

### 3. Authentication uses a dedicated test identity and stored session

Provision one least-privilege Supabase user containing no personal data. Generate Playwright
storage state through a setup project and store credentials only in GitHub/Vercel secrets; never
commit cookies or refresh tokens. Rotate the account/key together and document ownership.

### 4. Test data is explicit

The deterministic project seeds or selects a known upcoming event with coordinates and cleans up
only data it owns. The live map canary queries for any suitable event before opening the page. If
none exists, it skips with a message linked to FEAT-13's data-gauge output. A skip is not counted as
proof that the map works.

### 5. Locators follow accessible product contracts

Use roles, labels, visible event title/time, and keyboard activation. MapLibre canvas internals are
not a stable locator; expose an accessible list/button representation for pins if the existing UI
does not provide one. This improves accessibility and gives the journey a user-visible contract.

### 6. Langfuse is the live-carrying evidence

Tag live-canary turns with a dedicated test user and `e2e-live` tag. Assert the trace arrives with
model, latency, cost, tool calls, and cited event IDs. Trace failure must not break the user path but
does fail the observability assertion for the canary.

### 7. No ADR

This adopts existing testing, repository, gateway, and observability boundaries rather than making
a new product architecture decision.

## Risks / Trade-offs

- **The deterministic model stub misses provider-specific failures** → Keep the bounded live canary
  separate and scheduled.
- **A shared test account accumulates state** → Use only read behavior here and reset storage state
  from a controlled setup.
- **Map canvas is inaccessible to Playwright and keyboard users** → Add an accessible pin/list
  contract rather than CSS or MapLibre-internal selectors.
- **Empty inventory turns into a permanent skip** → FEAT-13 owns a critical inventory gauge; report
  the skip alongside it.
- **User-test redesign invalidates locators** → Do not implement selectors until that test finishes;
  retain behavior-level acceptance criteria.

## Migration Plan

1. Complete the Berlin user test.
2. Move/copy the approved OpenSpec change into `SolarFab/nachtkarte` and update the card link.
3. Provision the preview environment, test identity, storage-state workflow, and dedicated provider
   key/budget.
4. Land deterministic journeys as required preview checks.
5. Enable the live concierge canary manually, then schedule it after measuring stability and cost.

Rollback disables the live canary first, then removes the required browser check if it is flaky;
the accessible pin contract should remain.

## Open Questions

None in the architecture. Development remains blocked on the Berlin user test, preview environment,
test account, and dedicated OpenRouter budget.
