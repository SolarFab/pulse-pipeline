-- genre-dimension 1.1–1.4: give genre a real, filterable home.
--
-- Why: `subcategory` is one mutually-exclusive slot that conflates genre with
-- format, so a hip-hop club night files as `party` and the genre is lost
-- (normalize_subcategory() nulls any genre outside category='music'). Measured
-- consequence: 0 events behind the Hip-Hop filter while 9 existed that week.
-- Genre becomes a multi-valued, indexed dimension in its own events.genres column.

-- ── 1.1 taxonomy gains the genre dimension ───────────────────────────────────
-- kind distinguishes the row types that now share this table. For kind='genre'
-- and 'genre-group', `category_slug` carries the genre/group slug (it is the
-- table's generic leading slug column) and `subcategory_slug` stays NULL.
ALTER TABLE taxonomy ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'category';
ALTER TABLE taxonomy ADD COLUMN IF NOT EXISTS parent TEXT;
ALTER TABLE taxonomy ADD COLUMN IF NOT EXISTS aliases TEXT[] NOT NULL DEFAULT '{}';

UPDATE taxonomy
   SET kind = CASE WHEN subcategory_slug IS NULL THEN 'category' ELSE 'subcategory' END
 WHERE kind = 'category';  -- only the pre-migration default rows

ALTER TABLE taxonomy DROP CONSTRAINT IF EXISTS taxonomy_category_slug_subcategory_slug_key;
ALTER TABLE taxonomy DROP CONSTRAINT IF EXISTS taxonomy_kind_slugs_key;
ALTER TABLE taxonomy ADD CONSTRAINT taxonomy_kind_slugs_key
    UNIQUE NULLS NOT DISTINCT (kind, category_slug, subcategory_slug);

ALTER TABLE taxonomy DROP CONSTRAINT IF EXISTS taxonomy_kind_check;
ALTER TABLE taxonomy ADD CONSTRAINT taxonomy_kind_check
    CHECK (kind IN ('category', 'subcategory', 'genre', 'genre-group'));

-- Alias lookup (source vocabulary -> canonical slug) is a hot path in the pipeline.
CREATE INDEX IF NOT EXISTS taxonomy_aliases_idx ON taxonomy USING gin (aliases);
CREATE INDEX IF NOT EXISTS taxonomy_kind_idx ON taxonomy (kind) WHERE is_active;

-- ── 1.3 genre is its own column, not a slice of `tags` ───────────────────────
-- An audit of live data found 57% of genre-slug values in `tags` were noise from
-- years of free-text categorizer output (955 `singer-songwriter` on library
-- meetups, 604 `electronic` from the old RA hardcode incl. salsa classes). Only
-- the deterministic waterfall writes `genres`; the LLM free-tagger never does.
ALTER TABLE events ADD COLUMN IF NOT EXISTS genres TEXT[] NOT NULL DEFAULT '{}';
CREATE INDEX IF NOT EXISTS events_genres_gin ON events USING gin (genres);

-- ── 1.4 match_events gains p_genres (exact-recall genre filter) ──────────────
-- Filters constrain, the query ranks. p_genres is an array-overlap over genres:
-- every event carrying one of the requested genres is eligible, and the vector
-- ranks within that set — the property pure top-k similarity cannot provide
-- (measured: semantic-only recall 3–5/9 regardless of k).
DROP FUNCTION IF EXISTS match_events;

CREATE OR REPLACE FUNCTION match_events(
    query_embedding  TEXT DEFAULT NULL,
    p_query_text     TEXT DEFAULT NULL,           -- raw query for lexical title boost
    p_category       TEXT DEFAULT NULL,
    p_subcategory    TEXT DEFAULT NULL,
    p_genres         TEXT[] DEFAULT NULL,         -- canonical genre slugs; overlap over genres
    p_date_from      TIMESTAMPTZ DEFAULT now(),
    p_date_to        TIMESTAMPTZ DEFAULT now() + INTERVAL '14 days',
    p_neighborhood   TEXT DEFAULT NULL,
    p_venue          TEXT DEFAULT NULL,
    p_family         BOOLEAN DEFAULT FALSE,
    p_outdoor        BOOLEAN DEFAULT FALSE,
    p_free           BOOLEAN DEFAULT FALSE,
    p_max_price_cents INTEGER DEFAULT NULL,
    p_lat            DOUBLE PRECISION DEFAULT NULL,
    p_lng            DOUBLE PRECISION DEFAULT NULL,
    p_radius_km      DOUBLE PRECISION DEFAULT 1.5,
    p_limit          INTEGER DEFAULT 10
)
RETURNS TABLE (
    id UUID, title TEXT, venue_name TEXT, start_time TIMESTAMPTZ,
    category TEXT, subcategory TEXT, price TEXT, neighborhood TEXT,
    genres TEXT[], distance_km DOUBLE PRECISION
)
LANGUAGE sql STABLE AS $$
    WITH base AS (
        SELECT e.*,
            CASE WHEN p_lat IS NOT NULL AND e.lat IS NOT NULL THEN
                6371 * acos(least(1.0,
                    cos(radians(p_lat)) * cos(radians(e.lat::float8)) *
                    cos(radians(e.lng::float8) - radians(p_lng)) +
                    sin(radians(p_lat)) * sin(radians(e.lat::float8))))
            END AS dist_km
        FROM events e
        WHERE e.is_active
          AND e.start_time >= p_date_from
          AND e.start_time <= p_date_to
          AND (p_category     IS NULL OR e.category = p_category)
          AND (p_subcategory  IS NULL OR e.subcategory = p_subcategory)
          AND (p_genres       IS NULL OR e.genres && p_genres)
          AND (p_neighborhood IS NULL OR e.neighborhood ILIKE '%' || p_neighborhood || '%')
          AND (p_venue        IS NULL OR e.venue_name ILIKE '%' || p_venue || '%')
          AND (NOT p_family  OR e.family_friendly)
          AND (NOT p_outdoor OR e.outdoor)
          AND (NOT p_free    OR e.free_entry)
          AND (p_max_price_cents IS NULL OR e.price_cents IS NULL
               OR e.price_cents <= p_max_price_cents)
    )
    SELECT b.id, b.title, b.venue_name, b.start_time, b.category, b.subcategory,
           b.price, b.neighborhood, b.genres, b.dist_km
    FROM base b
    WHERE (p_lat IS NULL OR (b.dist_km IS NOT NULL AND b.dist_km <= p_radius_km))
    ORDER BY
        -- lexical title hit trumps everything (works even for unembedded events)
        CASE WHEN p_query_text IS NOT NULL AND length(p_query_text) >= 4
                  AND b.title ILIKE '%' || p_query_text || '%' THEN 0 ELSE 1 END,
        CASE WHEN query_embedding IS NOT NULL
             THEN b.embedding <=> query_embedding::vector(1536) END ASC NULLS LAST,
        CASE WHEN query_embedding IS NULL AND p_lat IS NOT NULL THEN b.dist_km END ASC NULLS LAST,
        b.start_time ASC
    LIMIT least(greatest(p_limit, 1), 20)
$$;

GRANT EXECUTE ON FUNCTION match_events TO anon, authenticated;

-- The map API reads through this view, which does not inherit new columns.
DROP VIEW IF EXISTS events_with_coords;
CREATE VIEW events_with_coords AS
 SELECT e.id, e.title, e.venue_name, e.venue_id,
    COALESCE(v.lat, e.lat) AS lat, COALESCE(v.lng, e.lng) AS lng,
    COALESCE(v.neighborhood, e.neighborhood) AS neighborhood,
    COALESCE(v.address, e.address) AS address,
    e.start_time, e.end_time, e.category, e.subcategory, e.tags, e.description,
    e.price, e.price_cents, e.image_url, e.source, e.source_url, e.source_id,
    e.source_tags, e.submitted_by, e.submission_link, e.status, e.fingerprint,
    e.quality_score, e.is_active, e.created_at, e.updated_at, e.genres
   FROM events e LEFT JOIN venues v ON e.venue_id = v.id;

GRANT SELECT ON events_with_coords TO anon, authenticated;
