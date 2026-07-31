-- unify-taxonomy 2.1: cross-cutting facets on events + categorizer confidence.
-- Additive only; defaults keep every existing row valid. Facets filter only when TRUE.

ALTER TABLE events ADD COLUMN IF NOT EXISTS family_friendly     BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE events ADD COLUMN IF NOT EXISTS outdoor             BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE events ADD COLUMN IF NOT EXISTS free_entry          BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE events ADD COLUMN IF NOT EXISTS category_confidence DECIMAL(3,2);

-- Partial indexes: facet toggles query WHERE facet = TRUE on active upcoming events.
CREATE INDEX IF NOT EXISTS events_family_friendly_idx ON events (start_time) WHERE family_friendly;
CREATE INDEX IF NOT EXISTS events_outdoor_idx         ON events (start_time) WHERE outdoor;
CREATE INDEX IF NOT EXISTS events_free_entry_idx      ON events (start_time) WHERE free_entry;
