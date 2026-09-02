## Context

Pulse is two repositories: this repository owns the Python pipeline, while `web/` is a nested,
gitignored checkout of `SolarFab/nachtkarte`. A workflow in this repository cannot observe web
changes. The present pipeline workflow installs unlocked dependencies with pip and runs pytest
only. The web repository has its own workflow but currently runs Vitest only, while its build hides
TypeScript errors.

GitHub Actions minutes are an external prerequisite for useful CI. Required-check enforcement is a
repository-setting concern and may depend on the account plan, but the checks themselves can be
made honest before enforcement is enabled.

## Goals / Non-Goals

**Goals:**

- Give each repository an always-present, deterministic CI check covering the code it owns.
- Use the committed lockfiles and fail on lint, tests, types, or production-build failures.
- Keep required check names stable so branch protection can refer to them.

**Non-Goals:**

- Cross-repository path filtering, Playwright, live-service tests, dependency scanning, or a Next.js
  upgrade.
- Making a Notion workflow a merge gate.

## Decisions

### 1. CI is split by repository, with stable aggregate check names

`nachtkarte-pipeline` gets one `pipeline` job that runs `uv sync --frozen --extra dev` followed by
`make check`. `nachtkarte` gets one `web` job that runs `npm ci`, lint, an explicit `typecheck`
script, Vitest, and `next build`.

Both jobs run on every pull request in their repository. Conditional path jobs were rejected: a
required check that is absent on some PRs can leave merges waiting forever, and repository-level
separation already removes almost all irrelevant work.

### 2. Existing failures are repaired before the gate is declared complete

Remove `typescript.ignoreBuildErrors` and the unsupported `eslint` key, add
`"typecheck": "tsc --noEmit"`, then repair the surfaced errors in the same repository. A green
build achieved by suppression does not satisfy the requirement.

### 3. Branch protection is the last, separable step

After both workflows have completed successfully at least once on their default branch, configure
the stable `pipeline` and `web` checks as required where the GitHub plan permits it. Until Actions
minutes are restored, the card remains blocked in Architecture even though this design is complete.

### 4. No ADR

This applies the existing repository boundary and toolchain; it does not introduce a new system
boundary or architectural policy.

## Risks / Trade-offs

- **Existing lint/type debt makes the first web run red** → Treat those failures as required work,
  not a reason to restore suppression.
- **Check names drift and break branch protection** → Name jobs `pipeline` and `web` explicitly and
  treat renaming as a repository-settings migration.
- **Actions remain unavailable** → Keep local `make check` and npm verification as evidence, but do
  not claim the CI acceptance criterion until hosted checks execute.
- **Two PRs are required** → Cross-link the pipeline and web cards/PRs; each repository owns its own
  implementation and check.

## Migration Plan

1. Restore an Actions billing budget.
2. Land the pipeline workflow change and observe a successful `pipeline` check.
3. Land the web workflow/config/debt repair in `SolarFab/nachtkarte` and observe a successful `web`
   check.
4. Configure required checks where supported and test with a deliberately failing PR.

Rollback removes required-check enforcement first, then reverts the workflow commit. Type-error
suppression must not be restored as a rollback mechanism.

## Open Questions

None in the technical design. GitHub Actions billing/minutes remains the external blocker.
