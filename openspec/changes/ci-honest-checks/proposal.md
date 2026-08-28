# CI runs the checks it claims to

## Why
`.github/workflows/tests.yml` runs one command: `pytest tests/`. No Ruff, no `web/` in any form,
and `pip install -e ".[dev]"` instead of the locked `uv` environment — so CI does not even test the
dependency set you develop against.

A green check currently means "the Python unit tests passed against whatever pip resolved today".
An external review found 17 ESLint errors, a failing `tsc --noEmit`, and a production build that
only succeeds because `next.config.ts` sets `typescript.ignoreBuildErrors: true` — all in code CI
had marked green.

Who benefits: anyone merging. Today a passing check is not evidence, so every reviewer must
re-run everything locally to know anything.

## What Changes
- Python job runs `make check` (Ruff + pytest) against `uv sync --frozen`
- Web job runs `npm ci`, lint, `tsc --noEmit`, unit tests and `next build`
- `next.config.ts` stops suppressing type errors, and drops the `eslint` key the installed Next.js
  does not accept — that key is itself one of the current `tsc` failures
- Both jobs become required status checks

## Capabilities
### Modified Capabilities
- `ci` — the checks executed match the checks claimed.

## Impact
`.github/workflows/tests.yml`, `next.config.ts`, and whatever existing lint/type failures surface.
No runtime behaviour change.

## Non-goals
Playwright, database integration tests, dependency scanning, the Next.js 16.3.3 upgrade. Separate
tickets. Branch protection needs GitHub Pro on a private repo and is tracked separately.
