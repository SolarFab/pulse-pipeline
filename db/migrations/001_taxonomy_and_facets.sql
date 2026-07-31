-- unify-taxonomy §1.1 + §2.1 — additive only, safe for the live app.
-- Apply deliberately (not auto): python db/apply_schema.py --migration 001
-- (or paste into the Supabase SQL editor).

-- ── Canonical taxonomy table (§1.1) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS taxonomy (
    id               SERIAL PRIMARY KEY,
    category_slug    TEXT NOT NULL,
    subcategory_slug TEXT,                -- NULL row = the category itself
    label_de         TEXT NOT NULL,
    label_en         TEXT NOT NULL,
    sort_order       INTEGER NOT NULL DEFAULT 0,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (category_slug, subcategory_slug)
);

-- Public reference data: readable by everyone, writable by nobody (service role only).
ALTER TABLE taxonomy ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS taxonomy_read_all ON taxonomy;
CREATE POLICY taxonomy_read_all ON taxonomy FOR SELECT USING (TRUE);

-- ── Facet columns on events (§2.1) ──────────────────────────────────────────
ALTER TABLE events ADD COLUMN IF NOT EXISTS family_friendly     BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE events ADD COLUMN IF NOT EXISTS outdoor             BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE events ADD COLUMN IF NOT EXISTS free_entry          BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE events ADD COLUMN IF NOT EXISTS category_confidence DECIMAL(3,2);

CREATE INDEX IF NOT EXISTS events_family_idx  ON events (family_friendly) WHERE family_friendly;
CREATE INDEX IF NOT EXISTS events_outdoor_idx ON events (outdoor)         WHERE outdoor;
CREATE INDEX IF NOT EXISTS events_free_idx    ON events (free_entry)      WHERE free_entry;
