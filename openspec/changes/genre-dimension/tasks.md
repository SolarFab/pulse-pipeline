# Genre Dimension — Tasks

## 1. Vocabulary & schema (migration 008)

- [x] 1.1 Add `kind`, `parent`, `aliases text[]` to `taxonomy`; backfill kind for existing rows
- [x] 1.2 Seed genre + genre-group rows: `data/ra_genres.json` minus format words (`club`), plus coarse concert genres (rock, pop, indie, metal, punk, schlager, klassik, folk, world) under ~14 umbrellas; Eventbrite aliases ("Hip Hop / Rap"→hip-hop, "EDM / Electronic"→electronic, …) — 15 groups / 94 genres seeded
- [x] 1.3 Create GIN index on `events.tags`
- [x] 1.4 Recreate `match_events` with `p_genres text[] DEFAULT NULL` (`AND e.tags && p_genres` when set); GRANT unchanged
- [x] 1.5 Mirror additive taxonomy columns in `pulse-discovery-agent/schema.sql` (contract sync) — no-op: the contract has no `taxonomy` table (venues/events/publishers/discovery only), and the `events` change is index-only

## 2. Pipeline population

- [x] 2.1 Genre vocabulary + aliases in `pipeline/genres.py` (the seed source for the DB; the web app reads the table). A DB round-trip in the pipeline for data it just seeded would be circular — `test_ra_vocabulary_is_covered` guards drift instead
- [x] 2.2 Alias mapping pass: canonicalize source_tags matches into `tags` (eventbrite, jazzity, huxleys)
- [x] 2.3 `detect_genres()` keyword detector (facets.py pattern, DE+EN, conservative) wired into the scrape pass in `scrapers/base.py`
- [x] 2.4 Rausgegangen scraper: capture the real category slug (16 values) into source_tags instead of URL slugs
- [x] 2.5 Categorizer: inject whitelist into prompt; filter output genres against vocabulary; log rejects
- [x] 2.6 Backfill script: run alias mapping + detector over active future events (no LLM); report per-source genre coverage
- [x] 2.7 Tests: detector precision cases (DE+EN, no-signal, veto), alias mapping, categorizer filter

## 3. Concierge & map API

- [x] 3.1 `getTaxonomy()` returns genres; `search_events` schema gains `genres` enum param
- [x] 3.2 Pass `p_genres` through in tools.ts; extend relax order (category/subcategory → genres) and the relaxed-note; discovery-miss only after full relax
- [x] 3.3 System prompt: add genre worked example ("hip hop tonight" → genres:['hip-hop'] + query); update example 1 wording
- [x] 3.4 `/api/events`: accept `genres` param (comma-separated, overlap filter) alongside legacy `tag`
- [x] 3.5 Tests: tools.test.ts relax-order cases; route param parsing

## 4. Verification

- [x] 4.1 Re-run hip-hop ground-truth recall — 18 events returned for the hip-hop family (hip-hop/r-and-b/trap/afrobeats/dancehall/reggaeton) Fri–Sun, incl. every event the concierge missed on 06.08 (Rhythm Fusion, Analog Beats, Giri, Afrotrain, VIBEZ!)
- [x] 4.2 Genre coverage: **39%** of music+nightlife future events carry ≥1 genre (610/1581) — below the 70% target. The earlier 68% was measured against contaminated `tags`; 39% is the precise number. Gap is non-RA sources (kulturdaten has no genre vocabulary, rausgegangen genre only in prose) — closing it needs Eventbrite subcategory capture + artist enrichment (PRD §5.3)
- [ ] 4.3 (deploy-gated) Live concierge spot-check ("hip hop tonight or tomorrow?") + Langfuse trace review
