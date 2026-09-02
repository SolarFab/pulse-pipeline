# Development — phase 5 · 🟣 Claude

Skills: `openspec-apply-change`, `tdd` (+ `langfuse` if `Touches LLM`,
`vercel-react-best-practices` if `Touches web`)

- **Enter:** an approved plan.
- **Do:** branch `feat/FEAT-nn-slug`, work the task list with `/opsx:apply`, tests alongside the
  code. Close your own loop against `make check` — hand over evidence, not assurances.
- **Leave:** PR open and CI green.

If `Touches LLM`, instrument as you build. Adding traces afterwards means shipping a change nobody
can observe, which is how Finding 13 happened: one wrong answer, five silent defects, no gauge.

If `Touches web`, that is a **separate PR in `SolarFab/nachtkarte`** — `web/` is its own repository,
nested here and gitignored. Its lint, test and build run there, not in this repo's CI.

Environment quirk: `git commit` fails from an unactivated shell because the pre-commit hook calls
bare `pre-commit`. Use `uv run git commit …`.
