-- ── match_events: resolve location through the venue, like the map already does ──
--
-- The map reads `events_with_coords`, which LEFT JOINs venues and COALESCEs the
-- location. match_events read `FROM events e` directly and did not. Same data,
-- two access paths, only one with the fallback — so the concierge was blind to
-- every event whose coordinates live on the venue row rather than the event row.
--
-- Measured on 2026-08-11, future active events (22,104 total):
--     events.lat IS NULL                          12,798   (58%)
--     COALESCE(events.lat, venues.lat) IS NULL       290    (1%)
-- The concierge therefore saw 42% of the catalogue on any geo-filtered search,
-- while the map showed 99%. A "was geht Sonntag in Kreuzberg mit Kind" query
-- returned one wrongly-tagged open-air screening and missed the actual children's
-- event two streets away, because that event's coordinates sit on its venue.
--
-- The same applies to `neighborhood` (3,903 future events have none of their own),
-- so it is coalesced too.
--
-- COALESCE ORDER MATTERS, and it is the opposite of the view's. The view prefers
-- the VENUE value; here the EVENT's own value wins and the venue only fills gaps.
-- 707 future events disagree with their venue, and the event is right in the case
-- that dominates: "The Makery" is a roving organiser whose ~450 events happen all
-- over Berlin, while its venue row says "Prenzlauer Berg" for every one of them.
-- Venue-first would have relabelled a Kreuzberg workshop as Prenzlauer Berg —
-- turning a fix for missing data into a regression on present data. Event-first is
-- strictly additive: it can only fill a NULL, never overrule a known value.
-- (The map's view has the same venue-first bug for those events; out of scope here.)
--
-- NOT changed: the radius clause still requires a known distance, so the 276
-- events with no coordinates anywhere stay out of an explicit radius search.
-- "Within 1.5 km" must not silently include events of unknown location; at 1%
-- the honest exclusion is cheap. Fixing those is a data task, not a query task.
--
-- The join cannot multiply rows: venues.id is the primary key.

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
            COALESCE(e.neighborhood, v.neighborhood) AS eff_neighborhood,
            CASE WHEN p_lat IS NOT NULL AND COALESCE(e.lat, v.lat) IS NOT NULL THEN
                6371 * acos(least(1.0,
                    cos(radians(p_lat)) * cos(radians(COALESCE(e.lat, v.lat)::float8)) *
                    cos(radians(COALESCE(e.lng, v.lng)::float8) - radians(p_lng)) +
                    sin(radians(p_lat)) * sin(radians(COALESCE(e.lat, v.lat)::float8))))
            END AS dist_km
        FROM events e
        LEFT JOIN venues v ON e.venue_id = v.id
        WHERE e.is_active
          AND e.start_time >= p_date_from
          AND e.start_time <= p_date_to
          AND (p_category     IS NULL OR e.category = p_category)
          AND (p_subcategory  IS NULL OR e.subcategory = p_subcategory)
          AND (p_genres       IS NULL OR e.genres && p_genres)
          AND (p_neighborhood IS NULL
               OR COALESCE(e.neighborhood, v.neighborhood) ILIKE '%' || p_neighborhood || '%')
          AND (p_venue        IS NULL OR e.venue_name ILIKE '%' || p_venue || '%')
          AND (NOT p_family  OR e.family_friendly)
          AND (NOT p_outdoor OR e.outdoor)
          AND (NOT p_free    OR e.free_entry)
          AND (p_max_price_cents IS NULL OR e.price_cents IS NULL
               OR e.price_cents <= p_max_price_cents)
    )
    SELECT b.id, b.title, b.venue_name, b.start_time, b.category, b.subcategory,
           b.price, b.eff_neighborhood, b.genres, b.dist_km
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

-- The join walks events -> venues by FK; without this the planner scans venues
-- for every filtered event set.
CREATE INDEX IF NOT EXISTS events_venue_id_idx ON events (venue_id);
