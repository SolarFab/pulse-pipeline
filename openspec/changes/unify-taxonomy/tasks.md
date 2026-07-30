# Tasks — Unify Taxonomy

Sequenced so the live app renders correctly after every step. **[db]** = Supabase migration,
**[pipeline]** = Python, **[web]** = Next.js (separate repo `nachtkarte`).

## 1. Canonical source (additive — zero user impact)

- [x] 1.1 [db] Migration: `taxonomy(category_slug, subcategory_slug, label_de, label_en, sort_order, is_active)`; readable by anon (public reference data)
- [x] 1.2 [pipeline] Idempotent seed script: `taxonomy.py` → `taxonomy` table (8 categories incl. `sports-wellness`, ~40 subcategories; `family` and legacy `outdoors` rows seeded `is_active = false`-ready but active until step 4)
- [x] 1.3 [pipeline] Document the tag freeze in `taxonomy.py` (tags = embed-text enrichment only)

## 2. Facets (additive — zero user impact)

- [x] 2.1 [db] Migration: `events.family_friendly`, `events.outdoor`, `events.free_entry` BOOLEAN DEFAULT FALSE + `events.category_confidence` DECIMAL
- [x] 2.2 [pipeline] Categorizer: keyword-based facet detection (DE+EN signal lists per design) + confidence emission, in the existing categorization pass
- [ ] 2.3 [pipeline] Backfill script: facets + confidence for all existing active events
- [x] 2.4 [pipeline] Unit tests: facet detection (kid-friendly market, open-air cinema, free-entry gig, no-signal event stays false)

## 3. Consumers read the canonical source (no visible change yet)

- [ ] 3.1 [web] Load taxonomy from the DB (cached); render existing chips from it (same 9 chips as today — including `family` until step 4)
- [ ] 3.2 [web] Concierge: `search_events` tool enum (category + subcategory) generated from the canonical taxonomy; delete the hand-rolled keyword/genre tables in `chat/route.ts`
- [ ] 3.3 [web] Scan route: category line in the prompt generated from the canonical taxonomy
- [ ] 3.4 [web] Verify: chips, chat filtering, and scan behave identically to before (no regression)

## 4. Realignment (the one user-visible step)

- [ ] 4.1 [pipeline] Re-filing script: `family` events → topical category + `family_friendly = true` (subcategory heuristics; leftovers → `culture` + flag for review); `outdoors/outdoor-cinema` → `culture/cinema` + `outdoor = true`; remaining `outdoors` → `sports-wellness`
- [ ] 4.2 [pipeline] Dry-run mode prints the full re-filing plan (event → old → new) for review before writing
- [ ] 4.3 [db] Execute re-filing; deactivate `family` + legacy `outdoors` rows in `taxonomy`
- [ ] 4.4 [web] Switch UI to 8 chips + "kid-friendly" / "outdoor" / "free" toggles; onboarding `family` pick maps to the facet
- [ ] 4.5 [web] Verify no orphaned categories: every active event's category exists among active taxonomy rows

## 5. Quality loop (depends on `event-embeddings` from the preference-feed change)

- [ ] 5.1 [pipeline] Audit script: kNN(10) by embedding; ≥70% neighbour-category mismatch → review list with suggested category (read-only; never auto-re-files)
- [ ] 5.2 [pipeline] Review list also includes low-confidence categorizations; wire into the nightly cleanup output/log
- [ ] 5.3 [pipeline] Report per-category embedding coherence (precision@k from the benchmark harness) as the taxonomy quality metric

## 6. Validation

- [ ] 6.1 Cross-check: grep confirms no category list exists outside the canonical source (web + pipeline)
- [ ] 6.2 `make lint && make test` green; web build green
- [ ] 6.3 Datenschutz/docs unaffected (no new personal data; facets are event properties)
