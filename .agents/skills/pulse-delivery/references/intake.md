# Intake — phases 0 and 1 · 🧑 Fabian

Skills: `pulse-delivery`

## 0 · Backlog
- **Enter:** the idea exists. Nothing else required.
- **Do:** decide whether it is real.
- **Leave:** it is worth specifying.

## 1 · Ready
- **Enter:** the Definition of Ready below is met.
- **Do:** create the GitHub issue carrying problem, criteria, edge cases and non-goals. Set `Risk`,
  `Touches LLM`, `Touches web` on the card.
- **Leave:** the issue exists and its link is on the card.

## Definition of Ready

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
