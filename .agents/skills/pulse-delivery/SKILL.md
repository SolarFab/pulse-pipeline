---
name: pulse-delivery
description: The Pulse delivery lifecycle — the eleven phases a change moves through, who owns each one (Fabian, Claude, Codex or automation), which skills each phase needs, and the Definition of Ready and Done. Use when starting, specifying, reviewing, implementing, verifying or closing any change, and whenever a card's phase needs updating.
---

# Pulse delivery pipeline

GitHub is the source of truth. The Notion **Pulse Delivery** board is the view — it records where
work stands, it does not gate anything. The real gates are CI, required checks, and human judgment.

- Board: https://app.notion.com/p/2e04556297ab40d7a24556f1fc02c52c
- Notion data source: `ab84fad6-44f8-47af-bedc-641692b48518`
- Sync workflow: `.github/workflows/notion-sync.yml` (present in both GitHub repos)

Every change is a card with an ID like `FEAT-12`. That ID goes in the branch
(`feat/FEAT-12-slug`), the PR title, and the commits. It is the only thread linking ticket, spec,
ADR, PR and deploy.

## Who owns which phase

The rule underneath: **whoever produces an artifact never grades it.**

| Phase | Owner | Skills |
|---|---|---|
| `0 · Backlog` | 🧑 Fabian | — |
| `1 · Ready` | 🧑 Fabian | pulse-delivery |
| `2 · Spec` | 🟣 Claude | pulse-delivery, openspec-propose |
| `3 · Spec Review` | 🟢 Codex | pulse-delivery, openspec-explore |
| `4 · Architecture` | 🟢 Codex | openspec-explore, improve-codebase-architecture, openspec-update-change |
| `5 · Development` | 🟣 Claude | openspec-apply-change, tdd |
| `6 · Review` | 🟢 Codex | pulse-delivery, tdd, improve-codebase-architecture |
| `7 · Verification` | 🟣 Claude | webapp-testing |
| `8 · Deployment` | 🧑 Fabian | — |
| `9 · Post-deploy` | ⚙️ automated | — |
| `10 · Closed` | 🟣 Claude | openspec-archive-change, openspec-sync-specs |

Plus, wherever the card declares them: **`langfuse`** on every LLM-touching phase from 2 onward,
**`vercel-react-best-practices`** at 5, 6 and 7 for web work.

Phase 7 is the one deliberate exception to the produce/grade rule — Claude verifies its own
implementation because the work there is mechanical (run the evals, open the preview). If
verification starts rubber-stamping, move it to Codex.

## Who writes the phase to Notion

`notion-sync.yml` derives four phases from PR events. **Never set these by hand** — you will fight
the workflow:

| Set automatically by | Phase |
|---|---|
| PR opened / reopened, or review requesting changes | `5 · Development` |
| PR ready for review, or review requested | `6 · Review` |
| Review approved | `7 · Verification` |
| PR merged | `8 · Deployment` |

Everything else is written by whoever owns the phase. Phase strings must match **exactly**,
including the `·` (U+00B7) and the spaces around it.

Set `Blocked` (checkbox) rather than inventing a phase — the phase a card stalled in is the
information you would otherwise lose.

## Declared at intake, not discovered later

Three card properties change what the pipeline requires. All are set at phase 1:

- **`Risk`** — Low skips `4 · Architecture` and usually `7 · Verification`. Medium runs the full
  line. High runs everything plus a human production approval at 8.
- **`Touches LLM`** — any model call, prompt, embedding or eval. Pulls `langfuse` in **from phase 2
  onward**. Observability is a requirement, not a late step: an acceptance criterion nobody can
  observe cannot be verified, span shape and cost budget are architecture decisions, and you
  instrument while building rather than after.
- **`Touches web`** — changes in `SolarFab/nachtkarte`, which is a separate repository.

## The phases

### 0 · Backlog — 🧑 Fabian
- **Enter:** the idea exists. Nothing else required.
- **Do:** decide whether it is real.
- **Leave:** it is worth specifying.

### 1 · Ready — 🧑 Fabian
- **Enter:** the Definition of Ready below is met.
- **Do:** create the GitHub issue carrying problem, criteria, edge cases and non-goals. Set `Risk`,
  `Touches LLM`, `Touches web`.
- **Leave:** the issue exists and its link is on the card.

### 2 · Spec — 🟣 Claude
- **Enter:** a ready ticket.
- **Do:** `/opsx:propose` writes `openspec/changes/<name>/` — proposal, spec deltas, task list. If
  `Touches LLM`, the acceptance criteria must say what will be observable in traces.
- **Leave:** proposal and tasks exist, `Spec` link is on the card.

### 3 · Spec Review — 🟢 Codex
- **Enter:** there is a spec to read.
- **Do:** review **the spec, not code**. Does it solve the stated problem? Are the criteria
  testable? Are the non-goals real? Correcting a paragraph costs a minute; correcting a 900-line
  diff costs an afternoon.
- **Leave:** approved, or back to 2 with specific objections.

### 4 · Architecture — 🟢 Codex
- **Skipped for Low risk.**
- **Enter:** an approved spec touching structure, data, a security boundary, or a new dependency.
- **Do:** read the proposal against the repo and the rules in `AGENTS.md`. Answer one question —
  does this violate a decision already made, or does it *make* a new one? If it makes one, write
  the ADR before any code exists. Name the anti-pattern explicitly, so a later refactor cannot
  quietly undo the reasoning.
- **Leave:** plan accepted, `ADR` link on the card if one was needed.

### 5 · Development — 🟣 Claude
- **Enter:** an approved plan.
- **Do:** branch `feat/FEAT-nn-slug`, work the task list with `/opsx:apply`, tests alongside the
  code. Close your own loop against `make check` — hand over evidence, not assurances.
- **Leave:** PR open and CI green.

### 6 · Review — 🟢 Codex
- **Enter:** CI passes. Not before — do not spend a review pass on code that does not build.
- **Do:** review the diff against the spec and `AGENTS.md`. Correctness, security (rules 1 and 2),
  tests that assert behaviour rather than mocks, scope creep, unrelated changes. Report findings;
  do not fix.
- **Leave:** approved. **Or back to 5** — normal, and counted in `Repair attempts`.

### 7 · Verification — 🟣 Claude
- **Enter:** the code is approved.
- **Do:** the preview deployment, E2E where it exists, and the golden-set evals. This asks a
  different question from Review: not *is this code good* but *does the acceptance criterion hold
  for a user*.
- **Leave:** every acceptance criterion demonstrably met. **Or back to 5.**

### 8 · Deployment — 🧑 Fabian
- **Enter:** verified.
- **Do:** merge. Low and Medium deploy automatically; High waits for your go.
- **Leave:** live.

### 9 · Post-deploy — ⚙️ automated
- **Enter:** it shipped.
- **Do:** smoke checks, the nightly quality gauges, and the traces. Watch for what only production
  reveals.
- **Leave:** stable, nothing to roll back.

### 10 · Closed — 🟣 Claude
- **Enter:** stable in production.
- **Do:** `/opsx:archive <change>` then `/opsx:sync`, so `openspec/specs/` describes the system as
  it now is.
- **Leave:** nothing. This is the end, and the phase most often skipped — skipping it is why a spec
  folder fills with proposals and stops describing the product.

## Definition of Ready — before a card leaves `1 · Ready`

- [ ] Problem stated, not just a solution
- [ ] Who benefits and how
- [ ] Acceptance criteria that are testable — "When \<trigger\>, the system shall \<response\>"
- [ ] Edge cases considered
- [ ] Dependencies named
- [ ] Security and privacy implications considered (OWASP LLM Top 10, GDPR — see `AGENTS.md`)
- [ ] **Does this touch a model?** If yes, tick `Touches LLM` and say what must be observable
- [ ] **Does this touch the web app?** If yes, tick `Touches web` — that is a separate repository
- [ ] Non-goals written down
- [ ] `Risk` assigned

Without these, an agent implements a fuzzy request precisely. That is the expensive failure.

## Definition of Done — before a card reaches `10 · Closed`

1. `make check` passes (ruff + pytest)
2. Web changes are a **separate PR in `SolarFab/nachtkarte`** — `web/` is its own repo, nested and
   gitignored here. Its lint/test/build run there.
3. The diff is reviewed against the acceptance criteria, not just for style
4. No unrelated changes rode along
5. If `Touches LLM`: traces appear in Langfuse and the golden-set eval shows no regression
6. Docs and specs updated
7. **`/opsx:archive <change>` then `/opsx:sync`** — not done until `openspec/specs/` matches reality

Step 7 is the one that gets skipped. When it is, `openspec/changes/` fills with proposals and the
spec folder stops describing the product. That has already happened here once.

## The repair loop

Bouncing `6 → 5` or `7 → 5` is normal — that is review doing its job. The sync increments
`Repair attempts` each time.

**Cap at 3.** On the third the workflow ticks `Blocked` automatically. Stop, write the diagnosis on
the card, hand it to a human. Two agents passing work back and forth without a limit is how a
ticket quietly becomes expensive.

A bounce all the way back to `2 · Spec` means the specification was wrong, not the code. Note it —
it is the signal that the spec review gate is being rushed.

## Loading caveat

This skill lives in `.agents/skills/pulse-delivery/`, symlinked into `.claude/skills/`, so Codex and
Claude read the same file. It only loads when the agent is started from inside a repo that has it —
running from the `pulse/` workspace root loads none of this repo's skills or `/opsx:*` commands.
