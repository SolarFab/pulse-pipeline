# event-embeddings

## ADDED Requirements

### Requirement: Vector storage enabled
The system SHALL enable the `pgvector` extension on the Supabase database and store a
fixed-dimension embedding vector for each event.

#### Scenario: Extension and column present
- **WHEN** the schema migration has run
- **THEN** the `vector` extension is installed AND the `events` table has an `embedding` column of the embedder's dimension AND an approximate-nearest-neighbour index (HNSW or IVFFlat) exists on it

### Requirement: Events embedded at ingest
The pipeline SHALL compute and store an embedding for every event as it is written, so no
active event lacks an embedding.

#### Scenario: New event gets an embedding
- **WHEN** the pipeline upserts a new event
- **THEN** an embedding derived from its title, description, category and tags is stored on that row

#### Scenario: Text unchanged, no re-embed
- **WHEN** an event is re-scraped and its embed-relevant text is unchanged
- **THEN** the existing embedding is reused and no new embedding call is made

### Requirement: Swappable embedder
The embedding model SHALL be selectable via configuration (not hard-coded), and the stored
model identifier SHALL be recorded so a model change can trigger a re-embed.

#### Scenario: Changing the embedder
- **WHEN** the configured embedding model differs from the model recorded on an event
- **THEN** that event is flagged for re-embedding

### Requirement: Backfill of existing events
The system SHALL provide a one-off backfill that embeds all existing active events.

#### Scenario: Backfill completes
- **WHEN** the backfill runs against a database of already-ingested events
- **THEN** every active event ends with a non-null embedding
