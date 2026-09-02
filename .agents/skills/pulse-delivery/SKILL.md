---
name: pulse-delivery
description: The Pulse delivery lifecycle — the eleven phases a change moves through, who owns each one (Fabian, Claude, Codex or automation), and which reference to read for the phase you are in. Use when starting, specifying, reviewing, implementing, verifying, releasing or closing any change, and whenever a card's phase needs updating.
---

# Pulse delivery pipeline

GitHub is the source of truth. The Notion **Pulse Delivery** board is the view — it records where
work stands, it does not gate anything. The real gates are CI, required checks, and human judgment.

- Board: https://app.notion.com/p/2e04556297ab40d7a24556f1fc02c52c
- Notion data source: `ab84fad6-44f8-47af-bedc-641692b48518`
- Sync workflow: `.github/workflows/notion-sync.yml` (in both GitHub repos)

Every change is a card with an ID like `FEAT-12`. That ID goes in the branch
(`feat/FEAT-12-slug`), the PR title, and the commits. It is the only thread linking ticket, spec,
ADR, PR and deploy.

## Who owns which phase

The rule underneath: **whoever produces an artifact never grades it.** Claude makes, Codex reviews,
Fabian owns the two ends.

| Phase | Owner | Read |
|---|---|---|
| `0 · Backlog`, `1 · Ready` | 🧑 Fabian | `references/intake.md` |
| `2 · Spec` | 🟣 Claude | `references/spec.md` |
| `3 · Spec Review` | 🟢 Codex | `references/spec.md` |
| `4 · Architecture` | 🟢 Codex | `references/architecture.md` |
| `5 · Development` | 🟣 Claude | `references/development.md` |
| `6 · Review` | 🟢 Codex | `references/review.md` |
| `7 · Verification` | 🟣 Claude | `references/verification.md` |
| `8 · Deployment`, `9 · Post-deploy`, `10 · Closed` | 🧑 Fabian → ⚙️ → 🟣 Claude | `references/release.md` |

**Read only the reference for the phase you are acting on.** Each names the skills that phase needs
and the exact entry and exit conditions.

Phase 7 is the one deliberate exception to the produce/grade rule — Claude verifies its own
implementation because the work there is mechanical. If verification starts rubber-stamping, move it
to Codex.

## Who writes the phase to Notion

`notion-sync.yml` derives four phases from PR events. **Never set these by hand** — you will fight
the workflow:

| Set automatically by | Phase |
|---|---|
| PR opened / reopened, or review requesting changes | `5 · Development` |
| PR ready for review, or review requested | `6 · Review` |
| Review approved | `7 · Verification` |
| PR merged | `8 · Deployment` |

**A PR carrying only specs, ADRs or docs must be labelled `spec-only`** — the sync then makes no
phase change. Create it with the label (`gh pr create --label spec-only`): labelling afterwards
cannot undo the `opened` event, so the sync corrects the card back to `2 · Spec` instead, and the
history still shows a phase it was never really in.

The label is opt-out on purpose: `chore/`, `docs/` and `fix/` branches are frequently real
implementations here, so a branch-name rule would be wrong more often than right.

Everything else is written by whoever owns the phase. Phase strings must match **exactly**,
including the `·` (U+00B7) and the spaces around it.

## Declared at intake, and they change the route

Set at phase 1. Forgetting one silently disables the rules that depend on it.

- **`Risk`** — Low skips `4 · Architecture`. Medium runs the full line. High runs everything plus an
  explicit go from Fabian *before* the merge.
- **`Touches LLM`** — any model call, prompt, embedding or eval. Pulls `langfuse` in **from phase 2**,
  not phase 7. An acceptance criterion nobody can observe cannot be verified.
- **`Touches web`** — changes in `SolarFab/nachtkarte`, a separate repository. Pulls
  `vercel-react-best-practices` in at 5, 6 and 7.

## Blocked cards

`Blocked` is a checkbox, not a phase. Tick it and leave the card where it is, so the phase it
stalled in is not lost. **A blocked card is still owned by whoever owns its phase** — keep going up
to the point where the dependency actually bites.

## The repair loop

Bouncing `6 → 5` or `7 → 5` is normal — that is review doing its job. The sync increments
`Repair attempts` each time.

**Cap at 3.** On the third the workflow ticks `Blocked` automatically. Stop, write the diagnosis on
the card, hand it to a human. Two agents passing work back and forth without a limit is how a ticket
quietly becomes expensive.

A bounce all the way back to `2 · Spec` means the specification was wrong, not the code. Note it —
it is the signal that the spec review gate is being rushed.

## Changes that span both repos

`web/` is a separate repository and a card carries one `GitHub PR`. A feature touching both the
pipeline and the web app is **two cards**, one per repo, each with its own PR driving its own phase.
Same title, cross-linked. One card cannot run through two repos — the sync would overwrite one PR
link with the other and the phases would fight.

## Loading caveat

This skill lives in `.agents/skills/pulse-delivery/`, symlinked into `.claude/skills/`, so Codex and
Claude read the same files. It only loads when the agent starts from inside a repo that has it —
running from the `pulse/` workspace root loads none of this repo's skills or `/opsx:*` commands.
