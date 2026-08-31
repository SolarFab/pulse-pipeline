# AGENTS.md — Pulse

Always-on conventions for AI agents (and humans) working in this repo. Read this first.
(Claude Code loads it via the `CLAUDE.md` symlink → this file.)

## What Pulse is
An event-discovery web app for Berlin: an interactive map of concerts, markets, nightlife,
kids events and pop-ups, plus an AI concierge you ask in natural language. Internal/legacy
name: **NachtKarte**.

## Repo layout
- `web/` — the app: **Next.js 16 (App Router, TypeScript)**, deployed on Vercel.
- `scrapers/` + `pipeline/` — the **Python** data pipeline (scrape → normalize → categorize → dedup → upsert).
- `db/` — database schema + helpers (Supabase Postgres + PostGIS).
- `openspec/` — spec-driven change docs (see "Specs" below).

## Commands
Pipeline (from repo root): `make install`, `make lint`, `make format`, `make test`, `make scrape`,
`make run SCRAPER=<name>`. Web: run inside `web/` with the app's own package scripts.
Prefer `make` / `uv run …` over raw `python`.

## Conventions
- **Python pipeline:** managed with **uv** (locked via `uv.lock`) — add deps with `uv add`, never
  edit a requirements file. Lint/format with **Ruff**; **pre-commit** runs it on every commit.
  Validate scraped data with **Pydantic** models (`pipeline/normalizer.py`). Tests with **pytest**;
  keep them green.
- **Web:** Next.js App Router + TypeScript. The `vercel-react-best-practices` skill applies to
  React/Next.js work — follow it.
- Keep secrets in `.env` (git-ignored) + the host's secret store. **Never commit secrets, and never
  put secrets in an LLM prompt.**

## Data model (key tables)
`events`, `venues` (public, read-only to clients) · `profiles`, `user_events` (interested/going),
`interested_venues`, `event_interest_counts` (per-user). The true schema lives in Supabase; manage
changes with the **Supabase CLI + versioned migrations** (don't hand-edit `db/schema.sql` and assume
it matches prod).

## Non-negotiable rules (load-bearing)
1. **RLS + anon key for per-user data.** All per-user tables (`profiles`, `user_events`,
   `interested_venues`, and any taste/interaction tables) MUST be read/written through the Supabase
   **anon key + the user's JWT** so Row Level Security scopes rows to `auth.uid()`. The
   **`service_role` key is server-only** (migrations/admin) and MUST NOT be on a user-request path —
   it bypasses RLS entirely. Every new per-user table gets `enable row level security` + owner policies.
2. **Scraped text is untrusted → indirect prompt injection.** Event descriptions come from scraped
   web pages. When they enter an LLM prompt (e.g. the concierge context), **delimit** them clearly,
   treat them as data not instructions, and harden the system prompt against override. Never let
   retrieved/scraped text carry the authority of a system instruction.
3. **Model-agnostic LLM access.** Route model calls through a gateway (Vercel AI SDK in web /
   LiteLLM in the pipeline), keep prompts in versioned files, and keep embeddings swappable. Don't
   hardcode a single provider deep in app code.
4. **Privacy (GDPR).** Person-level user data (incl. any "taste"/preference data) stays internal and
   is deletable on account deletion. Only aggregated signals are shareable.

## Security frame
Reason about changes against the **OWASP LLM Top 10** and four surfaces (app / model / data / infra):
LLM01 prompt injection (see rule 2), LLM02 sensitive-info disclosure (see rule 1). Rate-limit spend;
set a provider budget cap.

## Specs (OpenSpec)
Substantial features are planned as OpenSpec changes in `openspec/changes/<name>/`
(proposal → design → specs → tasks). Use `/opsx:propose "<idea>"` to start one and `/opsx:apply` to
implement. For small/mechanical work, ad-hoc is fine.

## Delivery pipeline
Every change is a card on the Notion **Pulse Delivery** board with an ID like `FEAT-12`. Put that ID
in the branch (`feat/FEAT-12-slug`), the PR title and the commits — it is the only thread linking
ticket, spec, ADR, PR and deploy.

GitHub drives phases 5, 6, 7 and 8 automatically (`.github/workflows/notion-sync.yml`). **You must
set the ones GitHub cannot see: 2 Spec, 3 Spec Review, 4 Architecture, 10 Closed.** Phase 10 means
`/opsx:archive` + `/opsx:sync` have run — a change is not done until the specs match reality.
See the `pulse-delivery` skill for the full phase contract.

## Repo boundaries — read this before touching web/
`web/` is **a separate git repository** (`SolarFab/nachtkarte`) nested inside this one, and it is in
this repo's `.gitignore`. Commits, branches and PRs for the web app happen *inside* `web/`, against
its own remote. Nothing under `web/` is ever staged from the repo root, and this repo's CI cannot
see it.

## Environment quirks
- **`git commit` fails from an unactivated shell**: the pre-commit hook calls bare `pre-commit`,
  which lives in `.venv/bin`. Use `uv run git commit …` or `source .venv/bin/activate` first.
- **The nightly scrape runs on the Hetzner box, not GitHub Actions** (`deploy/README.md`). The
  Actions `schedule:` in `scrape.yml` is deliberately commented out — both used 02:00 UTC and the
  `flock` in `run-scrape.sh` cannot see a GitHub runner. Do not "fix" the missing cron.

## Don'ts
- Don't use the `service_role` key for user requests.
- Don't pass raw scraped text to a model as if it were trusted instructions.
- Don't hand-edit `db/schema.sql` and assume it reflects the live DB — use migrations.
- Don't commit secrets, `.env`, or large data dumps.
