-- unify-taxonomy 1.1: canonical taxonomy table (single source for chips, tool enums, prompts).
-- Public reference data: readable by everyone, writable only via service role (seed script).

CREATE TABLE IF NOT EXISTS taxonomy (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category_slug    TEXT NOT NULL,
    subcategory_slug TEXT,                    -- NULL = the category-level row
    label_de         TEXT NOT NULL,
    label_en         TEXT NOT NULL,
    sort_order       INTEGER NOT NULL DEFAULT 0,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ DEFAULT now(),
    UNIQUE NULLS NOT DISTINCT (category_slug, subcategory_slug)
);

ALTER TABLE taxonomy ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "taxonomy is public reference data" ON taxonomy;
CREATE POLICY "taxonomy is public reference data"
    ON taxonomy FOR SELECT
    TO anon, authenticated
    USING (true);
