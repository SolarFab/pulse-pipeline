# Architecture — phase 4 · 🟢 Codex

Skills: `pulse-delivery`, `openspec-explore`, `improve-codebase-architecture`,
`openspec-update-change` (+ `langfuse` if `Touches LLM`)

**Skipped entirely for `Risk = Low`.**

- **Enter:** an approved spec touching structure, data, a security boundary, or a new dependency.
- **Do:** read the proposal against the repo and the rules in `AGENTS.md`. Answer one question —
  does this violate a decision already made, or does it *make* a new one? If it makes one, write the
  ADR in `docs/adr/` **before any code exists**. Name the anti-pattern explicitly ("do not introduce
  a second HTTP framework here"), so a later refactor cannot quietly undo the reasoning.
- **Leave:** plan accepted, `ADR` link on the card if one was needed.
- **If blocked:** the card stays here and stays yours. Tick `Blocked`, name the external dependency,
  and keep going up to the point where it actually bites. A blocked ticket is not an unowned one.

If `Touches LLM`, this phase decides the span shape, the cost and latency budget, and the rule that
tracing failures must never affect a user path.

`improve-codebase-architecture` scans existing code for refactoring opportunities — useful context,
but it looks backward. The judgement here is about a proposal, so treat its report as input, not as
the review.
