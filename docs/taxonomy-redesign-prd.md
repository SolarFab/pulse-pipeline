# Product Request: Taxonomy Redesign — Category × Format × Genre

**Status:** Draft for review · **Date:** 2026-08-06 · **Author:** research synthesis (Claude + FK)
**Companion docs:** [taxonomy-design-research.md](taxonomy-design-research.md) (IA theory), [taxonomy-audit.md](taxonomy-audit.md) (category mislabel audit), `openspec/` (implementation specs to follow)

---

## 1. Problem statement

A user asked the concierge for hip-hop events this week and got an "Offene Malstunde" at a
library. The map's Hip-Hop filter chip returns zero events. Meanwhile the database contained
**9 real hip-hop events that week** — findable by regexing descriptions, invisible to every
structured filter.

This is not a bug in one filter. It is a structural property of the taxonomy:

> **`subcategory` is one mutually-exclusive slot forced to hold six different dimensions:**
> genre (hip-hop, jazz), format (exhibition, club-night), topic (language, activism),
> audience (kids-program), venue type (gallery, playground), and setting (outdoor-cinema).

Because a hip-hop club night is *both* `party` (format) and `hip-hop` (genre), one always
loses — and in `nightlife`, where genre subcategories aren't even allowed
(`pipeline/categorizer.py` `normalize_subcategory()` nulls any genre paired with a
non-music category), genre **always** loses.

### Measured impact (live DB, 2026-08-06)

| Metric | Value |
|---|---|
| Active future events | 31,938 |
| Events this week with `subcategory IS NULL` | 805 / 1,433 (56%) |
| Nightlife events unclassified | 88% |
| Music events unclassified | 65% |
| Family events unclassified | 9% (works — vocabulary fits) |
| UI filter chips returning 0 events this week | 14 of 24 genre/type chips |
| `subcategory='hip-hop'`, entire future | 1 event (9 real ones exist this week alone) |
| `subcategory='electronic'`, entire future | 1 event (RA feeds ~215 club events/week) |
| Subcategories with ≤2 future events | 19 of 40 (5 with zero, ever) |

Coverage is *inverse* to user interest: nightlife and music — the categories people filter
by taste — are the least classified, because the vocabulary structurally can't hold the answer.

Secondary problems the redesign must also fix:

1. **Taxonomy is triplicated** — Postgres `taxonomy` table, `web/src/lib/types.ts`,
   `pipeline/categorizer.py` — plus dirty values already in prod (`"flea market"` w/ space).
2. **Scrapers destroy source signal** (see §3): RA genre exists upstream but is never
   requested; Rausgegangen categories are never captured; Eventbrite's format axis is
   flattened into tag soup.
3. **Naming collision:** `profiles.genres` already stores *category* keys (onboarding), and
   `notify_genres` likewise. The word "genre" must be reclaimed carefully.

---

## 2. What our sources actually provide (signal audit)

Roughly half of this problem is not classification — it's discarding structured metadata
our sources already deliver.

| Source | Events/wk | What it provides | What we keep today |
|---|---|---|---|
| kulturdaten.berlin | 673 | Fixed 20-term civic vocabulary (`attraction.category.*`, from Berlin's Bezirkskalender) — audience/topic, **no genre**. Plus organizer-level 2-tier taxonomy (~91 tags: `organization.category.Theater.Opera`, `.ConcertHalls.SymphonyOrchestra`…) and 9 accessibility tags | The 20 event tags ✓; organizer taxonomy and accessibility tags dropped |
| resident_advisor | 215 | **Per-event multi-genre tags from a curated 70-genre vocabulary**, free via the same unauthenticated GraphQL endpoint we already call (`genres { id name slug }`; filter `genre:{eq:"techno"}` works — Berlin techno = 595 upcoming) | Nothing — query omits the field; every event hardcoded `tags:["electronic","club"]`; descriptions truncated at 500 chars |
| rausgegangen | 140 | 16 stable category slugs (`konzerte-und-musik`, `party`, `ausstellung`…), one per event; free-form app tags | Nothing — `source_tags` are URL slugs (`best-mistake-47`) |
| eventbrite | 48 | 3 orthogonal axes: category (21) → subcategory (~30 music genres) + **format** (20: Party, Performance, Workshop…) + organizer tags | All flattened into one `source_tags` array mixing axes with hashtag noise (1,536 distinct values) |
| bandsintown | — | Genre lives on the **artist** (19 coarse buckets) but is **not in the public API v3** | n/a — enrichment would need artist-name lookup (MusicBrainz/Spotify) |

**Conclusion:** for the two highest-volume taste-driven sources (RA, Eventbrite), genre and
format can be captured **deterministically at scrape time** — no LLM, no backfill guessing.

---

## 3. Competitive analysis

### 3.1 The platforms we ingest

**Eventbrite** — three orthogonal, single-select axes per event + free tags:
category (21) → subcategory (~30 genres under Music), **format** (20 values: Conference,
Seminar, Festival, Performance, Screening, Gala, Workshop, Party, Rally, Tour…), tags (≤10).
A hip-hop club night is `Music × Hip Hop/Rap × Party` — the collision Pulse suffers is
representationally impossible. Format is a first-class *consumer* filter on their Berlin
search page (Category / Date / Neighborhood / Price / **Format** / Language), rendered as
top-4 values + "View more", no counts. Cautionary detail: their genre list has drifted
into near-duplicates (EDM vs Electronic vs DJ/Dance) — controlled vocabularies need an owner.

**Resident Advisor** — flat curated vocabulary of **70 genres** (`{id,name,slug}`), multi-tag
per event, promoter-assigned since 2023, optional (some events untagged). Genre filter + per-
genre landing pages in the UI. Available unauthenticated via `ra.co/graphql`. Their list
contains `Club` as a "genre" — even RA leaks format into genre; a whitelist needs a
no-format-words rule.

**Rausgegangen** (direct competitor; owned by DuMont since 2025, absorbed Ask Helmut) —
16 flat categories, one per event, deliberately **no genre** ("Genres kennen bei uns keine
Grenzen"); free-form tags in the app for search only. Filters: Heute/Morgen/Wochenende +
date picker; category = navigation, not multi-select. Discovery is curation-first
(Tagestipps). **Their taxonomy is our current model** — flat category, unstructured tags.

**kulturdaten.berlin** — categories are namespaced *tags* served from a versioned API
(120 total), inherited from the civic Bezirkskalender (hence `Polizei`, `Frauen`,
`Seniors` as categories). A civic-administrative vocabulary, not a discovery taxonomy —
justifies our own remapping layer. Genre-like depth exists only on *organizers*
(`organization.category.ConcertHalls.SymphonyOrchestra`) — usable for enrichment.

### 3.2 Music-native platforms (the pattern to follow)

| Platform | Model |
|---|---|
| **DICE** | `city / category / format / genre` as literal URL segments (`/browse/berlin/music/gig/techno`, `…/music/dj/hiphop`); typed tags (`music:gig`) separate from genre tags; app UX = personalized feed (follow-graph + Spotify sync), taxonomy as browse/SEO infrastructure |
| **Shotgun** | Event-level multi-genre (`["Techno","House"]`); city calendar axes = genre × date; small browsable umbrella set (~5–10) over finer tags |
| **Bandsintown** | Genre on the artist (19 buckets), events inherit; single-genre picker in app |
| **Songkick** | No genre anywhere; artists carry MusicBrainz IDs → external enrichment is the intended pattern |
| **Xceed** (Berlin nightlife) | Strongest German genre implementation: genre facet in filter URLs (`filters--music-genres_techno`), applies to events *and* clubs, stored user genre preferences |
| **NOCTAVA** (Berlin) | Event genre tags + **venue vibe tags** (underground/upscale/chill) + dress code + district |
| **THE CLUBMAP** (Berlin, app 03/2026) | Day/club/genre filters; venue-level music styles |

### 3.3 The German ticketing incumbents (the pattern to avoid)

Eventim: `Konzerte → {Clubkonzerte, HipHop & R'n'B, Electronic & Dance…}` — a *format*
("Clubkonzerte") sitting inside a genre list; single hierarchy, classic conflation.
berlin.de tickets: ~35 flat "genres" mixing Konzerte, HipHop, Oper, Party, Silvester,
Kochkurse at one level. Reservix: genre clusters at top level (Jazz/Rock/Pop vs Klassik)
with all stage arts lumped into "Bühne".

**No German platform separates category / format / genre. Doing it cleanly is differentiation,
not just correctness.**

### 3.4 Non-taxonomy discovery models (context)

Meetup (flat curated topics, many-to-many, ≤15, employee-approved; filters are logistics
only), Luma (8 auto-assigned categories; the real taxonomy is the follow-graph of
calendars/curators), Fever (editorial format-brands like Candlelight + a separate
**mood/"vibe" axis**), Time Out (pure editorial; the filter is the editor).
Two ideas worth stealing *later*: Fever's mood axis and the venue-level vibe/genre tagging
(NOCTAVA, CLUBMAP) — both are additive on top of a clean base taxonomy.

### 3.5 Standards alignment

Schema.org models event *kind* as the subclass (MusicEvent, ExhibitionEvent…, 23 types) and
puts `genre` **not on Event at all** — it lives on the performer/work — with `keywords`,
`audience`, `about` as separate properties, `isAccessibleForFree` as a boolean. Ticketmaster
(industry-standard ticketing): Segment→Genre→SubGenre tree **plus** separate Type/SubType
axis, multiple classifications per event with a `primary` flag. Genre ontologies
(MusicBrainz, Discogs, Spotify) are unanimous: **flat, multi-valued, curated whitelist; no
deep trees** (Spotify explicitly abandoned hierarchy). DACH open-data (DACH-KG/ThüCAT,
destination.one) converges on schema.org Event types — a format system, not genre.

---

## 4. Proposed model

Five orthogonal dimensions, one authoritative store.

| Dimension | Field | Cardinality | Vocabulary | Examples |
|---|---|---|---|---|
| **Category** | `category` (keep) | 1 of 9 | unchanged | music, nightlife, culture… |
| **Format** | `format` (new) | single, controlled ~16 | concert, club-night, party, open-mic, dj-set, exhibition, screening, performance, reading, workshop, class, market, festival, tour, talk, meetup, tasting | "what kind of gathering" |
| **Genre** | `genres text[]` (new) | multi, flat curated whitelist | seed = RA 70 (minus `Club`) ∪ coarse concert buckets (rock, pop, indie, metal/punk, schlager, klassik…) ≈ **~80 fine tags rolled up into ~14 umbrella groups** for UI | hip-hop, techno, house, jazz, classical, latin, afrobeats… |
| **Audience/attributes** | existing facets | booleans | family_friendly, outdoor, free_entry (+ later: accessibility from kulturdaten) | |
| **Topic** | `tags text[]` (keep) | multi, open | feeds embeddings + search, never a filter | |

Rules learned from the research:

1. **Genre whitelist contains no format words** (RA's `Club` mistake, NOCTAVA's
   `Live Music` mistake). Format words go in `format`.
2. **Two-tier genre, stored flat:** store fine slugs (`dub-techno`), roll up to umbrella
   groups (`electronic`) via the taxonomy table for UI display. Discogs Genre/Style and
   Shotgun's umbrella-browse model; avoids Spotify's unresolvable-tree problem.
3. **Multi-genre with optional primary** (Ticketmaster pattern) — first element = primary.
4. Venue-type subcategories (`gallery`, `playground`, `museum-for-kids`) move to the
   **venue** entity; setting subcategories (`outdoor-cinema`) become format `screening`
   + facet `outdoor`.
5. **Single source of truth:** the Postgres `taxonomy` table grows `kind`
   (category|format|genre|genre_group) + `parent` + `aliases text[]`; `types.ts` and
   `categorizer.py` constants are **generated** from it (build step), never hand-edited.
   The discovery-agent `schema.sql` contract is updated in the same change.

### Migration mapping for the 40 current subcategories

- genre-ish (jazz-blues, electronic, hip-hop, classical, rock-pop, world-folk, latin) → `genres[]`
- format-ish (live-concert, club-night, party, exhibition, cinema, theater, reading, festival, workshop-y, market-y, walking-tour…) → `format`
- audience (kids-program, family-event) → facet `family_friendly` (+ keep as display tag)
- venue (gallery, playground, museum-for-kids, bar-event) → venue entity / format
- topic (language, activism, tech-startup, community…) → `tags[]`
- `subcategory` column: kept read-only during transition (dual-write), dropped after UI cutover

---

## 5. Population strategy (in priority order)

1. **Scraper-native capture (deterministic, no LLM):**
   - RA: add `genres { name slug }` to the existing GraphQL query; delete the
     `["electronic","club"]` hardcode; raise the 500-char description truncation.
   - Eventbrite: request category/subcategory/format objects; map via pinned ID tables
     (one authenticated `/v3/categories|subcategories|formats` call to snapshot IDs).
   - Rausgegangen: scrape the real category slug (16 stable values) instead of URL slugs.
   - kulturdaten: keep the 20-tag mapping; **enrich genre from the organizer's**
     `organization.category.*` (SymphonyOrchestra → classical, Opera → opera…).
2. **Keyword detector** (`pipeline/facets.py` pattern — DE+EN regex over title +
   description + source_tags, conservative, idempotent, runs on every scrape → heals
   existing rows without re-scraping). Covers the 6-of-9 hip-hop events whose genre only
   exists in prose.
3. **Artist enrichment (later, optional):** lineup names → MusicBrainz/Spotify genre
   (Songkick/Bandsintown pattern). Only if 1+2 leave a measurable gap.
4. **LLM categorizer:** unchanged role, now filling `format` + suggesting genres *from the
   whitelist only*, for events steps 1–2 couldn't cover. Synonym map maintained in the
   taxonomy table (`aliases`), not in code.

Backfill = run step 2 over existing rows + re-map stored source metadata. No LLM spend.

---

## 6. Product surfaces

**Map filters:** category pills unchanged. Genre appears via **progressive disclosure** —
only when a genre-bearing context is active (music or nightlife category selected, or a
genre umbrella tapped from the "more" surface), never as a permanent extra row. Values
render with live counts for the active time window; zero-count values are hidden
(dead-end prevention — NN/g/Baymard). Multi-select within genre; truncate past ~6 visible
+ "more". Exact UI to be designed separately — this PRD fixes only the *rules*: no chip
that can return zero results, no genre chip outside a genre context.

**Concierge:** `search_events` gains `genres[]` (soft rank-boost + filter with automatic
one-step relaxation when 0 rows and a text query exists — the same "code enforces" pattern
as the date guards). System-prompt worked example #1 changes so genre goes into `query` +
`genres`, not `subcategory`. Zero-result discovery-miss logging skips relaxed-recovered
searches (stops false demand signals like "hip hop" being queued as unmet).

**Map API:** `/api/events` accepts `genres` (array-overlap via GIN index) alongside the
legacy `tag` param during transition.

**Onboarding/profile:** `profiles.genres` (which stores categories) is renamed
`profiles.categories`; a real `profiles.genre_prefs` becomes possible — future
personalization hook (Xceed/NOCTAVA store exactly this).

---

## 7. Risks & open questions

| Risk / question | Position |
|---|---|
| RA GraphQL is unofficial; genre field could vanish | Fallback = keyword detector (step 2) already covers it; degrade is graceful |
| Promoter tagging on RA is optional → gaps | Measured: fill rate to be logged per scrape; detector backfills |
| Genre vocabulary drift (Eventbrite's dupes) | Whitelist lives in taxonomy table with `aliases`; additions via review, not ad hoc; no-format-words rule |
| `profiles.genres` rename touches onboarding + notifications | Single migration + view alias during deploy window |
| Discovery-agent shared `schema.sql` contract | Update in same change; it reads venues / writes events+recipes — additive columns are backward-compatible |
| Should `food` + `markets` merge? (audit shows confusion: Markt am Maybachufer filed as markets, neighbors say food) | Out of scope here; note for a category-level review after format exists |
| Fever-style mood axis, venue vibe tags | Explicitly deferred — additive later, on top of clean base |

---

## 8. Success metrics

1. **Genre coverage:** ≥90% of RA events with ≥1 genre (from source); ≥70% of all
   music+nightlife events with ≥1 genre after backfill (today: ~3%).
2. **Dead ends:** 0 filter selections that can return zero results (structurally
   prevented); zero-result rate of concierge `search_events` calls with genre intent → <5%.
3. **Demand queue hygiene:** no genre terms in `discovery_requests` for genres we have
   events for.
4. **Single source of truth:** `types.ts` / `categorizer.py` taxonomy constants generated,
   0 hand-edited divergences (CI check).
5. Existing quality metric: embedding-neighbor disagreement (taxonomy-audit.md) re-run
   post-migration; format axis should reduce the culture↔meetups/family confusion pairs.

---

## 9. Sources

Ticketmaster Discovery API classification · schema.org/Event + /genre · Eventbrite v3
categories/subcategories/formats + Berlin consumer filters · RA GraphQL (`genres`,
`eventListings` genre filter; vocabulary snapshot in repo scratch: `ra_genres.json`) ·
Bandsintown Partner API docs + public OpenAPI · Songkick response objects · DICE browse
URLs + scraper docs · Shotgun scraper docs + store listing · Meetup topics help + API ·
Luma discover + help · Fever Berlin · Time Out London/Berlin · rausgegangen.de/berlin HTML
+ app blog · kulturdaten.berlin API v2 (`/api/tags`, 120 tags) + kulturdaten-api repo ·
tip-berlin.de Veranstaltungen filters · berlin.de/tickets/kategorien · Eventim/Reservix
category pages · Xceed Berlin filter URLs · NOCTAVA · THE CLUBMAP (Groove, 03/2026) ·
MusicBrainz genres blog · Discogs genre/style docs · Every Noise at Once · NN/g
(filters-vs-facets, filter-categories-values, applying-filters, progressive-disclosure) ·
Baymard filtering studies · Hearst, Flamenco faceted-search papers · DACH-KG/ThüCAT ·
destination.one.

Full URLs preserved in the research transcripts; key primary sources are linked from the
sections above where load-bearing.
