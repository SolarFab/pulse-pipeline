# Genre Dimension — Design

## Context

Genre currently has no queryable home: `subcategory` structurally excludes it outside
`category='music'` (`normalize_subcategory()` nulls the pair), and tags were source-vocabulary
soup until commit `da511f1` made RA emit canonical kebab genres. Retrieval today is
embeddings-first with strict filters; measured on the hip-hop ground truth: semantic-only recall
3–5/9 regardless of k, tag-overlap recall 9/9 where tags exist. The concierge (`match_events`
RPC + `search_events` tool) already has a relax-on-empty degrade for category/subcategory.
Evidence and competitive analysis: `docs/taxonomy-redesign-prd.md`.

Core principle (settled with FK 2026-08-06): the model must never write queries — knowledge lands
in the DB, capability lands in the fixed RPC, the LLM only translates intent to enum values.

## Goals / Non-Goals

**Goals:**
- Exact-recall genre filtering for concierge and map API over one canonical vocabulary.
- Deterministic genre population for ≥70% of music+nightlife events (LLM only as last resort).
- One source of truth: vocabulary + aliases live in the `taxonomy` table.

**Non-Goals:**
- Map filter UI (progressive disclosure design — separate change).
- `format` column / full subcategory retirement (PRD §6, later change).
- `profiles.genres` rename; artist-based enrichment (MusicBrainz/Spotify).

## Decisions

1. **Store genres in a dedicated `events.genres text[]` column.**
   *(Reversed during implementation — the original decision was to reuse `tags`.)* An audit of
   live data killed that shortcut: 57% of genre-slug values already in `tags` were noise —
   955 events tagged `singer-songwriter` (library senior meetups), 604 `electronic` (the old RA
   hardcode, incl. salsa classes), 241 `classical` (after-school gaming). `tags` carries years of
   free-text categorizer output that collides with genre names, and nothing distinguishes a legacy
   topic tag from a genuine genre assertion. Filtering genre over `tags` would have shipped a
   Classical filter returning "After School Gaming" — the same trust failure as the hip-hop
   incident, inverted. A separate column also closes recurrence: only the deterministic waterfall
   writes it, never the LLM free-tagger. `tags` stays free-form topic vocabulary and keeps feeding
   embeddings.
2. **Vocabulary + aliases in `taxonomy` table** (`kind` in category|subcategory|genre|genre-group,
   `parent` slug, `aliases text[]`). Seed: `data/ra_genres.json` (70 minus `club` — the
   no-format-words rule) + coarse concert genres (rock, pop, indie, metal, punk, schlager,
   klassik…) grouped under ~14 umbrellas. Eventbrite mappings live as aliases
   (`"Hip Hop / Rap"` → `hip-hop`). Alternative rejected: separate genres table — the taxonomy
   table already exists, is RLS-readable by the web app, and `getTaxonomy()` already caches it.
3. **`p_genres` is a strict filter with last-drop relax.** `match_events` adds
   `p_genres text[] DEFAULT NULL`; when set: `AND e.tags && p_genres`. Tool-side relax order
   on empty: drop category/subcategory first (existing), then genres, so a genre query never
   dead-ends but genre stays authoritative when populated. Alternative rejected: rank-boost
   only — surrenders the exact-recall property that motivated the change.
4. **Detector mirrors `facets.py`**: pure DE+EN regex over title+description+source_tags,
   conservative (no signal → no tag), idempotent, runs inside the scrape pass so existing rows
   heal without re-scraping. **Text detection is gated to music-ish categories**
   (music/nightlife/culture) — added after a senior meetup listing "Lesungen, Reiseberichte,
   klassische Musik" among its afternoon activities was tagged `classical`. That is a true keyword
   match and a false genre claim; the words appear in a menu, not as the billing. Source-asserted
   genres (promoter tags, Eventbrite subcategory) stay explicit and apply in any category. Patterns map to canonical slugs via the alias table, not hardcoded
   duplicates. LLM categorizer gets the whitelist injected into its prompt and its output
   filtered against it (belt and suspenders).
5. **Tool schema derives the genre enum from `getTaxonomy()`** exactly like categories today —
   no hardcoded list in web code (unify-taxonomy rule).

## Risks / Trade-offs

- [Genre coverage is 39% of music+nightlife, below the 70% target] → the 70% figure was set
  against contaminated `tags`; 39% is the honest precise number. Remaining gap is structural:
  kulturdaten publishes no genre vocabulary and rausgegangen carries genre only in prose.
  Closing it needs Eventbrite subcategory capture and artist-based enrichment (PRD §5.1, §5.3).
- [RA promoter tagging optional → untagged RA events invisible to genre filter] → detector layer
  covers description-borne genre; relax keeps them reachable via ranking; log fill-rate per scrape.
- [Alias drift (Eventbrite renames values)] → aliases in DB, updatable without deploy; unmatched
  source genres logged, not dropped.
- [match_events signature change] → drop/recreate in one migration (same pattern as 006);
  additive default-NULL param keeps existing web callers working during deploy window.
- [Discovery-agent schema contract] → additive columns only; update `schema.sql` in same PR.

## Migration Plan

1. Migration 008: taxonomy columns (`kind`,`parent`,`aliases`) + genre seed rows + GIN index on
   `events.tags` + `match_events` recreate with `p_genres`.
2. Pipeline: detector + alias mapping + categorizer whitelist (deploy any order — additive).
3. Backfill: run detector over existing active future events (script, no LLM).
4. Web: tool schema + prompt example + `/api/events` genres param (after 1 is live).
5. Rollback: `p_genres` default NULL means web can revert independently; migration is additive.
