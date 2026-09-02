# Release — phases 8, 9 and 10

## 8 · Deployment — 🧑 Fabian merges, the card follows

- **Enter:** the merge event. Fabian merges at the 7 → 8 boundary and `notion-sync.yml` then writes
  phase 8. Nobody sets this by hand, and **phase 8 does not mean "merge now"** — it means the change
  is deploying or live. `Risk = High` waits for Fabian's explicit go *before* the merge, not after.
- **Do:** watch the deploy.
- **Leave:** deployed and serving.

## 9 · Post-deploy — ⚙️ automated

- **Enter:** deployed.
- **Do:** smoke checks, the nightly quality gauges, the traces.
- **Leave — this is the trigger that wakes Claude for phase 10:** one healthy nightly run has
  completed *after* the deploy — `run-scrape.sh` reporting `ok` with gauges under threshold. For a
  change the nightly does not exercise (docs, CI, agent config), 24 hours with no new error in the
  traces or logs. Until that event, the card stays here.

Rollback is asymmetric and worth knowing before you need it: Vercel rolls back instantly, the
Hetzner pipeline does not, and applied database migrations do not at all.

## 10 · Closed — 🟣 Claude

Skills: `openspec-archive-change`, `openspec-sync-specs`

- **Enter:** stable in production, per the trigger above.
- **Do:** `/opsx:archive <change>` then `/opsx:sync`, so `openspec/specs/` describes the system as it
  now is.
- **Leave:** nothing. This is the end.

### Definition of Done

1. `make check` passes (ruff + pytest)
2. Web changes shipped as their own PR in `SolarFab/nachtkarte`
3. The diff was reviewed against the acceptance criteria, not just for style
4. No unrelated changes rode along
5. If `Touches LLM`: traces appear in Langfuse and the golden set shows no regression
6. Docs and specs updated
7. **`/opsx:archive` then `/opsx:sync`** — not done until `openspec/specs/` matches reality

Step 7 is the one that gets skipped. When it is, `openspec/changes/` fills with proposals and the
spec folder stops describing the product. That has already happened here once.
