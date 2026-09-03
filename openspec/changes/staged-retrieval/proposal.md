# Staged retrieval with progressive constraint relaxation

## Why

On 2 September a user asked for **comedy in Prenzlauer Berg** and was told there was nothing.
On 3 September the same question returned three events while the map showed more. Both answers
came from the same defect: the concierge treats every constraint as equally hard, and relaxes
only when a query returns literally zero rows.

The traces show what happened. Yesterday: two `match_events` calls, the first returning 0 rows.
Today: one call, three rows — and **three rows was enough to suppress relaxation**, even though
those three were simply the comedy events that happened to carry `subcategory = 'comedy'`.
Of 97 upcoming comedy events, **45 have no subcategory at all**. A taxonomy gate on a taxonomy
that is 46% incomplete is a filter that hides the catalogue.

The deeper problem is ordering. Retrieval currently takes a global vector top-N and applies
constraints afterwards, so a strong local match can be discarded before the location filter is
ever considered. Constraints must shape the search, not post-filter it.

## What Changes

Retrieval becomes **staged**, with constraints classified by how hard they really are:

- **Always hard** — date and time, active explicit price limits, availability, legal and access
  constraints. Never relaxed; relaxing them produces answers that are wrong, not merely broader.
- **Initially hard, relaxable** — neighbourhood, distance, venue.
- **Semantic by default** — comedy, romantic, underground, chill, experimental. Matched by meaning,
  never gated by a taxonomy filter.
- **Ranking signals, not filters** — category, subcategory, genres, title match, popularity.
- **Hard taxonomy only on explicit request** — a "Workshops only" UI toggle, not an inferred intent.

The loop: search with all constraints applied inside the query; if the result clears a **relevance
threshold**, answer. If not, relax exactly one constraint in a deterministic order and search again,
carrying forward what was relaxed. Answer honestly about what was widened.

> Tonight I couldn't find comedy in Prenzlauer Berg, but here are three strong options elsewhere.

## Two dependencies that would make this fire spuriously

**1. Location data is not yet trustworthy enough to be a stage-1 hard constraint.** For Prenzlauer
Berg the `neighborhood` label finds 188 upcoming events; the postcode already sitting in the address
finds 2,254. Some venues carry rounded, wrong coordinates — Bühnen Rausch is in Prenzlauer Berg and
is recorded about 2 km away in Mitte. If location stays hard at stage 1 against this data, the
relaxation ladder fires because the *data* is missing, not because the neighbourhood is empty, and
every answer becomes "nothing there, here's the rest of Berlin". **Blocked on the neighbourhood
ticket.**

**2. Duplicates corrupt the threshold.** 23% of upcoming events are duplicate rows, and 1,134
duplicate groups disagree about `subcategory`. Deduplication must happen **before** the limit and
before the relevance test, or three copies of one event will satisfy a "we found enough" check that
one event would not. **Blocked on the deduplication ticket.**

Both are prerequisites, not side quests. Shipping staged retrieval on the current data would
produce a system that relaxes constantly and counts duplicates as evidence.

## Non-goals

- Re-ranking models or a learned ranker. Ordering stays explainable.
- Changing the map.
- Multi-turn memory of previously relaxed constraints.
