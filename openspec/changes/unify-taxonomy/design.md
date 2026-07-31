# Design — Unify Taxonomy

## Shape

```
                 ┌────────────────────────────────────┐
                 │  taxonomy (DB table — canonical)   │
                 │  8 categories → ~40 subcategories  │
                 │  EN slug + DE/EN labels + sort     │
                 └───────┬────────────────────────────┘
     seeded from         │ read by
     pipeline/taxonomy.py│
   ┌─────────────────────┼──────────────────────────────────┐
   ▼                     ▼                                  ▼
 map chips          concierge search_events            scan route prompt
 (+ facet toggles)  tool enum (category, subcategory)  (category line generated)

 events: category, subcategory, family_friendly, outdoor, free_entry, category_confidence
```

## Key decisions

### 1. DB table as the single source (not a shared file)
`web/` and the pipeline are separate repos; the DB is already their only contract (same pattern as
the discovery-agent split). A `taxonomy` table crosses that boundary with no file syncing. The web
app reads it once and caches (taxonomy changes are rare); the pipeline seeds it idempotently from
`taxonomy.py`, which remains the human-edited source of truth in code review.

### 2. Categories = what it IS (one), facets = what it HAS (many)
Single-label `category` stays — chips need mutual exclusivity and ~1k events don't justify
multi-membership machinery (Airbnb-scale). Cross-cutting properties become booleans:

| Facet | Detection (categorizer pass, keyword-based) |
|---|---|
| `family_friendly` | "kinder", "familie", "family", "kids", age hints ("ab 3 Jahren") |
| `outdoor` | "open air", "draußen", "outdoor", venue types (park, market square) |
| `free_entry` | "eintritt frei", "free entry", "kostenlos", price == 0 |

False negatives are acceptable (toggle shows less, never wrong category); detection improves
incrementally.

### 3. Realignment: family → facet, outdoors → sports-wellness
- `family` events re-file into their true topical category (a kids' concert → `music` +
  `family_friendly`). Mapping: subcategory heuristics + keyword pass; leftovers → `culture` +
  facet, flagged for review.
- `outdoors` keeps only essence-level activity (sports, yoga-fitness, bike-tour, walking-tour →
  renamed slug `sports-wellness`); `outdoor-cinema` re-files to `culture/cinema` + `outdoor` facet.
- Sequencing (prod DB, no staging): (1) additive schema, (2) backfill facets, (3) web consumers
  read canonical table but keep old chip set, (4) re-file data, (5) switch chips to 8 + toggles.
  At every step the live app renders correctly.

### 4. Tag freeze
`TAG_KEYWORDS` stays in code and keeps enriching embed text (free signal), but is documented as
frozen: no new entries, no consumer reads it as taxonomy. The 633 tags are a pre-embeddings
retrieval mechanism; embeddings supersede them.

### 5. Quality loop (T-LEAF, solo-founder sized) — depends on `event-embeddings`
- **Audit:** for each event, take its k=10 nearest neighbours by embedding; if ≥7 carry a different
  category, flag as a miscategorization candidate. Output: a small weekly list (SQL + one script),
  feeding the existing nightly cleanup instead of heuristics.
- **Confidence:** categorizer emits `category_confidence` (keyword-hit strength). Low-confidence
  events appear in the same review list. No silent guessing.
- The embedding benchmark's precision@k per category doubles as a taxonomy coherence metric: a
  category that never clusters is incoherent by measurement, not opinion.

## Untrusted input note
Facet detection and categorization run over scraped text — keyword matching only, no LLM on this
path, so no new injection surface. The scan route's generated prompt line contains only our own
canonical slugs, never scraped content.

## Model-agnostic note
No model calls added. The concierge tool enum is generated data; whichever LLM sits behind the
gateway sees the same enum.
