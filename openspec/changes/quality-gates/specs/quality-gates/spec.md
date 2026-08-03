# quality-gates

## ADDED Requirements

### Requirement: Ingest-time field validation
The pipeline SHALL validate price (plausible range/currency; nonsense ranges dropped to null),
time (end after start, duration <24h, plausible hour for family events), and SHALL derive
neighborhood from PLZ/address when the source omits it.

#### Scenario: Nonsense price range
- **WHEN** a source yields "Free – 86.41 EUR"
- **THEN** the stored price is normalized or nulled, never displayed as-is

#### Scenario: Missing neighborhood with Berlin PLZ
- **WHEN** an event has address "…, 10245 Berlin" and no neighborhood
- **THEN** neighborhood = Friedrichshain is derived at ingest

### Requirement: Nightly quality gauges
A nightly job SHALL emit: unembedded-upcoming, unlinked-venues, invisible-on-map,
subcategory-usage vs taxonomy, duplicate-venue candidates, per-source freshness; each gauge
SHALL have a threshold that fails the job loudly when crossed.

#### Scenario: Embedding gap regrows
- **WHEN** unembedded-upcoming exceeds its threshold
- **THEN** the nightly run reports failure with the count (no more silent 3,401s)

### Requirement: Venue deduplication
Duplicate venue rows SHALL be merged (events relinked, coords-bearing row kept) with an alias
table preserving name variants for future matching.

#### Scenario: Case-variant duplicate
- **WHEN** "PUNCH L!NE CLUB BERLIN" and "Punch L!ne Club Berlin" both exist
- **THEN** one canonical row remains, the variant becomes an alias, events point at the canonical row
