# Link spec scenarios to tests with stable IDs

## Why
Scenarios and the tests covering them are connected by nothing. FEAT-9 shipped with six passing
tests and one requirement — venue linking still runs after the scrape — covered by none of them.
Nobody could see the gap because there was nothing to see it in.

Who benefits: the reviewer, who currently has to hold the spec and the test file side by side and
diff them mentally.

## What Changes
- Each scenario gets a stable ID
- Each test declares the ID(s) it covers
- CI reports scenarios without tests, and tests referencing scenarios that do not exist

## Capabilities
### New Capabilities
- `process` — traceability between specification and verification.

## Why not a separate verification document
A `verification.md` per change duplicates the scenarios that already exist in `specs/**/spec.md`,
and duplicated truth drifts. Six weeks later nobody knows which copy is current.

Naming the test function inside the spec is also wrong: it couples a normative requirement to an
implementation detail and breaks on every rename.

## Impact
Spec format convention, a pytest marker, a CI check. No runtime code.

## What this does NOT prove
A marker asserts that a test *claims* to cover a scenario. It cannot show the test checks the
right thing — a test can carry the ID and assert nothing meaningful, which is exactly the defect
FEAT-9 shipped with. Coverage here is necessary and not sufficient, and this change MUST NOT be
presented as making the review question redundant.

## Non-goals
Retrofitting IDs onto archived changes. New specs only; existing ones get IDs when touched.
