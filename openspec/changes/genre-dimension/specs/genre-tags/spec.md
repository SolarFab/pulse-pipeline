# Genre Tags

## ADDED Requirements

### Requirement: Canonical genre vocabulary
The system SHALL maintain a curated genre vocabulary in the `taxonomy` table (`kind='genre'`),
each genre a kebab-case slug with an umbrella group (`parent`, `kind='genre-group'`) and an
`aliases text[]` mapping source vocabularies to the canonical slug. The vocabulary MUST NOT
contain event-format words (club, party, concert, live-music, festival).

#### Scenario: Alias resolves to canonical slug
- **WHEN** an Eventbrite event carries source tag "Hip Hop / Rap"
- **THEN** the pipeline maps it to canonical tag `hip-hop` via the alias table, and the raw value is preserved in `source_tags`

#### Scenario: Format word rejected from vocabulary
- **WHEN** a source vocabulary offers "Club" or "Live Music" as a genre
- **THEN** it is not admitted as a genre slug (it is a format, out of this vocabulary's scope)

### Requirement: Deterministic genre population waterfall
The pipeline SHALL populate genre tags in priority order: (1) scraper-native source genres,
(2) alias mapping of source tags, (3) a conservative DE+EN keyword detector over
title+description+source_tags, (4) LLM categorizer constrained to the vocabulary. Steps 1–3
MUST NOT call an LLM. The detector SHALL be idempotent and run on every scrape pass so
previously stored rows heal without re-scraping.

#### Scenario: Description-only genre is detected
- **WHEN** an event's description says "Hip-Hop, RnB und Trap" but its source provided no genre
- **THEN** after the scrape pass the event's tags include `hip-hop`

#### Scenario: No signal, no tag
- **WHEN** neither source metadata nor text contains a whitelisted genre signal
- **THEN** the event receives no genre tags (absence over guessing)

#### Scenario: LLM output is whitelist-filtered
- **WHEN** the categorizer proposes a genre not in the vocabulary
- **THEN** the value is dropped before upsert and logged for curation review
