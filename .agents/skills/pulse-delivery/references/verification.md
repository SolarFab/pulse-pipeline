# Verification — phase 7 · 🟣 Claude

Skills: `webapp-testing` (+ `langfuse` if `Touches LLM`,
`vercel-react-best-practices` if `Touches web`)

- **Enter:** the code is approved. The sync writes this on approval, so phase 7 is **never skipped**
  — what varies is how much work it takes.
- **Do:** the preview deployment, E2E where it exists, and the golden-set evals.
- **Leave:** verified and **awaiting Fabian's merge**. **Or back to 5.**

Review asked *is this code good*. This phase asks a different question: **does the acceptance
criterion hold for a user?**

## How much work

- **`Risk = Low` with neither `Touches LLM` nor `Touches web`** — satisfied by green CI alone.
  Record that on the card and move on. That is the whole rule; there is no "usually".
- **`Touches web`** — open the Vercel preview and walk the criterion by hand or with Playwright.
- **`Touches LLM`** — run the golden set in `eval/golden_set/` and confirm no regression, and check
  the traces actually appear in Langfuse. A model change that passes unit tests and degrades answers
  is the failure this catches.
