# Review — phase 6 · 🟢 Codex

Skills: `pulse-delivery`, `tdd`, `improve-codebase-architecture`
(+ `langfuse` if `Touches LLM`, `vercel-react-best-practices` if `Touches web`)

- **Enter:** CI passes. Not before — do not spend a review pass on code that does not build.
- **Do:** review the diff against the spec and `AGENTS.md`. **Report findings; do not fix.**
- **Leave:** approved. **Or back to 5** — normal, and counted in `Repair attempts`.

## What to check

| Dimension | Question |
|---|---|
| Requirements | Does it satisfy the acceptance criteria, all of them? |
| Correctness | Bugs, edge cases, race conditions |
| Security | AGENTS.md rule 1 (RLS + anon key, never `service_role` on a user path) and rule 2 (scraped text is untrusted — delimited, never authoritative) |
| Data | Migrations backward-compatible, integrity preserved |
| Tests | Do they assert behaviour, or 30 mocks passing and proving nothing? |
| Scope | Unrelated changes riding along |
| Maintainability | Duplication, unnecessary abstraction |

A reviewer told to find gaps will find some even when the work is sound. Flag only what breaks
correctness or a stated requirement; mark the rest optional. Chasing every finding produces
defensive code and tests for cases that cannot happen.
