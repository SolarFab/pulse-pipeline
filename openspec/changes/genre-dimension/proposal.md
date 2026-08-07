# Genre Dimension

## Why

The "hip-hop incident" (2026-08-06): the concierge and the map's Hip-Hop filter returned zero
events while 9 real hip-hop events existed in the DB that week. Root cause is structural — genre
has no home in the data model. `subcategory` is one mutually-exclusive slot where genre loses to
format every time (a hip-hop club night files as `party`, never `hip-hop`), and until today the RA
scraper overwrote real promoter genres with a hardcoded `["electronic","club"]`.

The scraper fix (commit `da511f1`) now lands canonical genre tags for RA events — but nothing
*consumes* them yet, and the other sources still speak three different genre vocabularies
(Eventbrite `Hip Hop / Rap`, organizer hashtags, nothing at all). Measured ceiling without this
change: semantic-only retrieval finds 3–5 of 9 relevant events; a populated genre filter finds 9/9
with exact precision. Full analysis: `docs/taxonomy-redesign-prd.md` §1–5.

## What Changes

- **Canonical genre vocabulary** in the `taxonomy` table (kind=`genre`, ~80 fine tags under ~14
  umbrella groups; seed = RA's 70-genre list minus format words + coarse concert genres). Aliases
  column maps source vocabularies (Eventbrite, hashtags) onto canonical slugs.
- **Genre population waterfall** (deterministic before LLM):
  1. scraper-native (RA: done; Eventbrite subcategory via alias mapping; rausgegangen category slug capture)
  2. keyword detector in `pipeline/facets.py` style (DE+EN regex over title+description+source_tags,
     conservative, idempotent, heals existing rows on every scrape)
  3. LLM categorizer constrained to the whitelist, only for leftovers
- **`match_events` RPC gains `p_genres text[]`** — array-overlap filter over `events.tags` (GIN
  index), with the existing relax-on-empty degrade extended to drop genres last.
- **Concierge `search_events` gains `genres` param** (enum from taxonomy) + system-prompt worked
  example; model translates "hip hop" → `genres:['hip-hop']` instead of relying on ranking alone.
- **Map API `/api/events` accepts `genres`** (array-overlap) alongside the legacy `tag` param.
  Map UI wiring is explicitly OUT of scope here (progressive-disclosure design is its own change).

## Capabilities

### New Capabilities
- `genre-tags`: canonical genre vocabulary, its population waterfall (scraper-native → alias
  mapping → keyword detector → LLM), and the no-format-words curation rule.

### Modified Capabilities
- `semantic-search`: retrieval gains an exact-recall genre filter layer — `p_genres` on
  `match_events`, `genres` on the concierge tool, genre-aware relax order.
- `taxonomy`: the taxonomy table gains `kind`/`parent`/`aliases` columns to host the genre
  vocabulary next to categories/subcategories.

## Impact

- DB: migration for `taxonomy` columns + seed rows; GIN index on `events.tags`; new
  `match_events` signature (drop/recreate, additive params — existing callers unaffected).
- Pipeline: `scrapers/eventbrite.py`, `scrapers/rausgegangen.py`, `pipeline/facets.py` (or new
  `pipeline/genres.py`), `pipeline/categorizer.py` (whitelist constraint).
- Web: `web/src/lib/ai/tools.ts`, `web/src/app/api/chat/route.ts` (prompt), `web/src/app/api/events/route.ts`.
- Contract: `pulse-discovery-agent/schema.sql` gets the additive taxonomy columns (backward-compatible).
- Out of scope: map filter UI, `format` column, `profiles.genres` rename (PRD §6–7 follow-ups).
