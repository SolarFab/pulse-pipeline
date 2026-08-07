# Taxonomy — genre rows

## ADDED Requirements

### Requirement: Taxonomy table hosts the genre dimension
The `taxonomy` table SHALL gain `kind` (category|subcategory|genre|genre-group), `parent`
(slug of the umbrella group for genres), and `aliases text[]` columns. Genre rows SHALL be
seeded from the curated vocabulary (`data/ra_genres.json` minus format words, plus coarse
concert genres). All consumers (concierge tool enum, pipeline detector/alias mapping,
categorizer whitelist) MUST derive the genre list from this table — no hardcoded copies.

#### Scenario: Single source of truth
- **WHEN** a genre is added or aliased in the taxonomy table
- **THEN** the concierge tool enum and the pipeline mapping pick it up without a code change

#### Scenario: Existing category rows unaffected
- **WHEN** the migration runs
- **THEN** existing category/subcategory rows keep their slugs and sort order, with `kind` backfilled accordingly

### Requirement: Map API genre parameter
`/api/events` SHALL accept a `genres` query parameter (comma-separated canonical slugs) filtering
by tags-overlap, alongside the legacy `tag` (subcategory) parameter, which remains unchanged
during the transition.

#### Scenario: Genre overlap query
- **WHEN** the map requests /api/events?genres=hip-hop,techno
- **THEN** events tagged with either genre are returned regardless of category
