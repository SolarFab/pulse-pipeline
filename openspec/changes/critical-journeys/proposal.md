# Two critical user journeys

## Why
Nothing checks that the product works end to end. The concierge returned `401 User not found` for
over a week; it was found by a person asking a question, not by any check. Separately, a missing
venue join made 58% of upcoming events invisible to search for months.

Who benefits: users in the Berlin test, who would otherwise be the detector.

## What Changes
Two Playwright journeys, each protecting a chain that has already broken in production:

1. The concierge answers with a real, clickable event
2. An upcoming event renders as a map pin and its detail view opens

## Capabilities
### New Capabilities
- `critical-journeys` — end-to-end coverage of the two paths whose failure is invisible from
  inside the codebase.

## Why only two
A larger suite written before the user test targets a UI the test is about to change. These two
are chosen because each has already failed silently in production. The rest waits until real usage
shows which paths matter.

## The boundary with data gauges
Journey 2 must not fail because the catalogue is empty — inventory belongs to `data-quality`. The
journey owns the rendering chain. Conflating them reports a UI defect when the problem is upstream.

## Impact
`web/` gains Playwright, a config and two spec files. Needs a test account and OpenRouter credit —
the concierge journey makes a real model call.

## Non-goals
Filters, login flows, saved events, responsive layouts, visual regression. After the user test,
informed by what people actually did.
