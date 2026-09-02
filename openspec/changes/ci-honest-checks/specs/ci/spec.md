# ci

## ADDED Requirements

### Requirement: CI validates both product repositories
Continuous integration SHALL execute the Python checks on every `nachtkarte-pipeline` pull request
and the web checks on every `nachtkarte` pull request. Each repository SHALL expose an always-present
stable check that can be required independently.

#### SC-CI-01: Python changes
- **WHEN** a pull request is opened in `nachtkarte-pipeline`
- **THEN** CI runs Ruff and pytest, and fails on either

#### SC-CI-02: Web changes
- **WHEN** a pull request is opened in `SolarFab/nachtkarte`
- **THEN** CI runs lint, type checking, unit tests and a production build, and fails on any

#### SC-CI-03: A failing check blocks the merge
- **WHEN** any required check fails
- **THEN** the pull request cannot be merged

### Requirement: CI uses the locked dependency set
The Python job SHALL install from `uv.lock`. Resolving dependencies freshly means CI tests a
different environment from the one developers and the Hetzner box run.

#### SC-CI-04: Locked install
- **WHEN** the Python job installs dependencies
- **THEN** it uses `uv sync --frozen`, and fails if the lock file is out of date

### Requirement: Type errors are not suppressed
The production build SHALL fail on TypeScript errors. `typescript.ignoreBuildErrors` exists to let
a broken build succeed, which is the opposite of what a build check is for.

#### SC-CI-05: A type error fails the build
- **WHEN** `tsc --noEmit` reports an error
- **THEN** CI fails, and `next build` does not mask it

#### SC-CI-06: The config itself type-checks
- **WHEN** `tsc --noEmit` runs
- **THEN** `next.config.ts` produces no error — it currently declares an `eslint` key the installed
  Next.js does not accept
