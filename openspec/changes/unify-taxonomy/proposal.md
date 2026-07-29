# Unify Taxonomy

## Why

The taxonomy currently exists in **four places** that already drift: the canonical
`pipeline/taxonomy.py` (9 categories, 44 subcategories, 633 tags), a hand-rolled keyword table in
`web/.../api/chat/route.ts`, a hardcoded enum inside the prompt of `web/.../api/events/scan/route.ts`,
and the filter chips in the map UI. The concierge doesn't know subcategories exist ("jazz" maps to
all of `music` although `music/jazz-blues` exists).

Beyond drift, the taxonomy conflates **three different axes** in one single-label field: topics
(music, food), formats (markets, workshops, meetups), and audience/setting (family, outdoors). The
result: a kid-friendly food market must *choose* between `food` and `family`, and users tapping the
"family" chip miss kid-friendly events filed elsewhere. Industry practice (Eventbrite's
category×format axes, Airbnb's multi-membership categories) separates these dimensions.

Finally, the 633-entry flat tag vocabulary is a pre-embeddings artifact: it exists to make "jazz
tonight" findable by keyword. Event embeddings (see `preference-feed` → `event-embeddings`) take
over that job.

## What Changes

- **One canonical source in the DB**: a `taxonomy` table (8 categories + ~40 subcategories, EN slugs
  + DE/EN display labels), seeded from `pipeline/taxonomy.py`. All consumers — map chips, concierge
  tool enum, scan prompt — derive from it. No more parallel lists.
- **Facets, not categories, for cross-cutting properties**: three booleans on `events` —
  `family_friendly`, `outdoor`, `free_entry` — set by the categorizer, filterable across every
  category. Bar for adding a facet later: "would it be a filter toggle in the UI?"
- **Category realignment**: retire `family` as a category (dissolves into the facet); slim
  `outdoors` to `sports-wellness` (essence-level activities only; the setting becomes the `outdoor`
  facet). Existing events are re-filed by a one-off migration.
- **Tag freeze**: the 633 tags stay as data (they enrich embed text) but are no longer maintained or
  extended; no consumer treats them as a taxonomy.
- **Quality loop (post-embeddings)**: an embedding-based audit flags events whose nearest neighbours
  mostly carry a different category (miscategorization candidates); the categorizer emits a
  confidence and low-confidence events land in a small review list instead of being silently filed.

## Capabilities

### New Capabilities
- `taxonomy` — the canonical taxonomy source, facet assignment, category realignment, and the
  taxonomy quality loop.

### Modified Capabilities
- None formally. (The `preference-feed` change is unaffected; its cold-start and eval labels simply
  read the canonical table. The audit tasks depend on `event-embeddings` landing first.)

## Impact

- **Database (Supabase):** new `taxonomy` table; three boolean columns on `events`; one-off
  re-filing of `family`/`outdoors` events. All schema steps are additive; the data re-filing is the
  only user-visible step and is sequenced last.
- **Pipeline (Python):** categorizer sets facets + confidence; seed script for the taxonomy table;
  re-filing migration script; audit script (needs embeddings).
- **Web (Next.js, separate repo):** chips + chat tool enum + scan prompt read the canonical
  taxonomy; a "kid-friendly" toggle replaces the `family` chip.
- **Cost:** zero LLM cost (facet detection is keyword-based in the existing categorizer pass).
- **Users:** strictly better filtering — "kid-friendly" works across all categories instead of
  being a silo. Chip set changes (9 → 8 + toggles) — visible, small.

## Non-goals

- **No full topic×format ontology** (Eventbrite-style two-axis model): over-engineering at ~1k
  events; embeddings carry cross-axis meaning. The mixed chip set is a documented, deliberate
  simplification: post-embeddings, the taxonomy is a UI artifact, not a knowledge model.
- **No new facets beyond the three** without the toggle test.
- **No tag cleanup project**: tags are frozen, not migrated.
- **No renaming of the remaining categories** (churn without user value).
