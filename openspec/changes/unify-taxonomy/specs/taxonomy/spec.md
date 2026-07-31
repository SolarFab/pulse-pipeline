# taxonomy

## ADDED Requirements

### Requirement: Single canonical taxonomy source
The system SHALL store the taxonomy (categories, subcategories, display labels DE/EN) in one
canonical database table, seeded idempotently from `pipeline/taxonomy.py`, and all consumers
(map filter chips, concierge tool enum, scan prompt) SHALL derive their category lists from it.

#### Scenario: Adding a subcategory propagates everywhere
- **WHEN** a new subcategory is added to the canonical source and seeded
- **THEN** the map chips, the concierge `search_events` enum, and the scan prompt include it without any consumer-side code change

#### Scenario: No parallel lists remain
- **WHEN** the web app resolves a free-text genre or renders filter chips
- **THEN** it uses the canonical taxonomy (directly or via embeddings), not a hardcoded keyword table

### Requirement: Cross-cutting properties are facets, not categories
The system SHALL represent audience/setting/price properties as boolean facets on events
(`family_friendly`, `outdoor`, `free_entry`), settable in any combination alongside exactly one
category, and the UI SHALL expose them as toggles that filter across all categories.

#### Scenario: Kid-friendly food market
- **WHEN** an event is a food market with child-oriented signals ("Kinderprogramm")
- **THEN** it is stored as `category = food` (or `markets`) with `family_friendly = true`, and appears under both the food/markets chip and the kid-friendly toggle

#### Scenario: Facet detection is conservative
- **WHEN** an event's text contains no facet signal
- **THEN** the facet remains false (false negatives are acceptable; no facet is guessed)

### Requirement: Category realignment
The system SHALL retire `family` as a category (events re-filed to their topical category with
`family_friendly = true`) and narrow `outdoors` to essence-level activities (`sports-wellness`),
re-filing setting-only members (e.g. outdoor cinema → `culture/cinema` + `outdoor = true`).

#### Scenario: Former family event
- **WHEN** the re-filing migration processes an event currently in `family` (e.g. a children's concert)
- **THEN** it ends with a topical category (`music`), `family_friendly = true`, and no event remains in `family`

#### Scenario: Live app never breaks mid-migration
- **WHEN** any single migration step (schema, backfill, re-filing, chip switch) has run and the next has not
- **THEN** the deployed app still renders correct chips and returns correct filter results

### Requirement: Tag vocabulary is frozen
The system SHALL keep existing tags only as internal enrichment (embed-text input) and SHALL NOT
extend the tag vocabulary or expose tags as a filtering taxonomy to any consumer.

#### Scenario: New genre appears in events
- **WHEN** events of a genre with no tag entry (e.g. a new music style) are ingested
- **THEN** no tag entry is added; retrieval of such events relies on embeddings

### Requirement: Taxonomy quality is measured
The system SHALL emit a categorization confidence per event and SHALL provide an embedding-based
audit that flags events whose nearest neighbours predominantly carry a different category; flagged
and low-confidence events SHALL surface in a review list rather than being silently re-filed.

#### Scenario: Misfiled event is caught
- **WHEN** an event's k nearest neighbours by embedding predominantly (≥70%) have a different category
- **THEN** the event appears on the review list with its suggested category, and its stored category is unchanged until reviewed

#### Scenario: Low-confidence categorization
- **WHEN** the categorizer's keyword evidence is below the confidence threshold
- **THEN** the event is filed with its best guess and appears on the review list
