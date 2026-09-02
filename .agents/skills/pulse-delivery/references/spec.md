# Specification — phases 2 and 3

## 2 · Spec — 🟣 Claude
Skills: `pulse-delivery`, `openspec-propose` (+ `langfuse` if `Touches LLM`)

- **Enter:** a ready ticket.
- **Do:** `/opsx:propose` writes `openspec/changes/<name>/` — proposal, spec deltas, task list.
  If `Touches LLM`, the acceptance criteria must say **what will be observable in traces**. A
  criterion nobody can observe cannot be verified later.
- **Leave:** proposal and tasks exist, `Spec` link on the card.

Label the PR `spec-only` if it carries specs and nothing else, or the sync will drag the card into
Development.

## 3 · Spec Review — 🟢 Codex
Skills: `pulse-delivery`, `openspec-explore`

- **Enter:** there is a spec to read.
- **Do:** review **the spec, not code**. Does it solve the stated problem? Are the criteria
  testable? Are the non-goals real? Does it contradict a decision already recorded in `AGENTS.md`
  or `docs/adr/`?
- **Leave:** approved, or back to 2 with specific objections.

Correcting a paragraph costs a minute; correcting a 900-line diff costs an afternoon. This is the
cheapest gate on the line — spend the time here.
