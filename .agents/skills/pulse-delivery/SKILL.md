---
name: pulse-delivery
description: The Pulse delivery lifecycle — the eleven phases a change moves through, which ones you must record on the Notion board, and the Definition of Ready and Done. Use when starting, advancing, reviewing or closing any change in this repo, and whenever a card's phase needs updating.
---

# Pulse delivery pipeline

GitHub is the source of truth. The Notion **Pulse Delivery** board is the view — it records where
work stands, it does not gate anything. The real gates are CI, required checks and human review.

- Board: https://app.notion.com/p/2e04556297ab40d7a24556f1fc02c52c
- Notion data source id: `ab84fad6-44f8-47af-bedc-641692b48518`
- Human-readable phase guide: the "Delivery Pipeline" page above the board

## Who sets what

`.github/workflows/notion-sync.yml` derives phases from PR events. **Never set these by hand** —
you will fight the workflow:

| Phase | Set automatically by |
|---|---|
| `5 · Development` | PR opened/reopened, or review requesting changes |
| `6 · Review` | PR marked ready for review, or review requested |
| `7 · Verification` | review approved |
| `8 · Deployment` | PR merged |

**You are responsible for the phases GitHub cannot observe:**
`0 · Inbox`, `1 · Ready`, `2 · Spec`, `3 · Spec Review`, `4 · Architecture`, `9 · Post-deploy`,
`10 · Closed`.

Phase strings must match exactly, including the `·` (U+00B7) and the spaces around it.

## Updating a card

Find the card by its `ID` property (type `unique_id`, prefix `FEAT`), then patch `Phase`.
Use the Notion MCP tools; `.github/scripts/notion_sync.py` is the reference implementation of the
lookup if you need it.

Set `Blocked` (checkbox) rather than inventing a phase — the phase a card stalled in is the
information you would otherwise lose.

## Risk tiers decide which phases apply

- **Low** — skip `4 · Architecture`, usually skip `7 · Verification`. Copy, styling, isolated bugs,
  config, small refactors.
- **Medium** — the full line. New features, API changes, new dependencies.
- **High** — every phase, plus a human production approval at 8. Anything touching auth, per-user
  data, migrations, permissions, secrets, or infrastructure. AGENTS.md rules 1 and 4 usually apply.

## Definition of Ready — before a card leaves `1 · Ready`

- [ ] Problem stated, not just a solution
- [ ] Who benefits and how
- [ ] Acceptance criteria that are testable, written as "When <trigger>, the system shall <response>"
- [ ] Edge cases considered
- [ ] Dependencies named
- [ ] Security and privacy implications considered (OWASP LLM Top 10, GDPR — see AGENTS.md)
- [ ] Non-goals written down
- [ ] Risk tier assigned

Without these, an agent implements a fuzzy request precisely. That is the expensive failure.

## Definition of Done — before a card reaches `10 · Closed`

1. `make check` passes (ruff + pytest)
2. Web changes are a **separate PR in `SolarFab/nachtkarte`** — `web/` is its own repo, nested
   and gitignored here. Its lint/test/build run there, not in this repo's CI.
3. The diff is reviewed against the acceptance criteria, not just for style
4. No unrelated changes rode along
5. Docs and specs updated
6. **`/opsx:archive <change>` then `/opsx:sync`** — the change is not done until `openspec/specs/`
   describes the system as it now is

Step 6 is the one that gets skipped. When it is, `openspec/changes/` fills with proposals and the
spec folder stops describing the product. That has already happened here once.

## The repair loop

Work bouncing `6 → 5` or `7 → 5` is normal — that is review doing its job. The sync increments
`Repair attempts` each time.

**Cap at 3.** On the third, the workflow ticks `Blocked` automatically. Stop, write the diagnosis
on the card, and hand it to a human. Two agents passing work back and forth without a limit is how
a ticket quietly becomes expensive.

A bounce all the way back to `2 · Spec` means the specification was wrong, not the code. Note it —
it is the signal that the spec review gate is being rushed.

## Loading caveat

This skill lives in `event-map/.claude/skills/`. It only loads when Claude Code is started from
inside `event-map/`. Running from the `pulse/` workspace root loads none of this repo's skills or
`/opsx:*` commands.
