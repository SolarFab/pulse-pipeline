-- NachtKarte Berlin — Supabase Schema
-- Run this in the Supabase SQL editor

-- Enable PostGIS for geospatial queries
CREATE EXTENSION IF NOT EXISTS postgis;

-- ─────────────────────────────────────────
-- VENUES
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS venues (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    lat             DECIMAL(10, 7) NOT NULL,
    lng             DECIMAL(10, 7) NOT NULL,
    neighborhood    TEXT,
    address         TEXT,
    venue_type      TEXT,           -- club, bar, gallery, park, market, etc.
    website_url     TEXT,
    instagram_handle TEXT,
    google_place_id TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (name, lat, lng)
);

-- ─────────────────────────────────────────
-- EVENTS
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    venue_name      TEXT NOT NULL,
    venue_id        UUID REFERENCES venues(id) ON DELETE SET NULL,

    -- Location
    lat             DECIMAL(10, 7),
    lng             DECIMAL(10, 7),
    neighborhood    TEXT,
    address         TEXT,

    -- Timing
    start_time      TIMESTAMPTZ NOT NULL,
    end_time        TIMESTAMPTZ,
    is_recurring    BOOLEAN DEFAULT FALSE,
    recurrence_rule TEXT,           -- iCal RRULE format

    -- Classification
    category        TEXT NOT NULL,  -- music, nightlife, food, culture, entertainment, wellness, social, market
    subcategory     TEXT,
    tags            TEXT[],

    -- Details
    description     TEXT,
    price           TEXT,           -- "Free", "€12", "from €8"
    price_cents     INTEGER,        -- 0 = free, for sorting
    image_url       TEXT,

    -- Source tracking
    source          TEXT NOT NULL,  -- "kulturdaten", "eventbrite", "rausgegangen", "community", etc.
    source_url      TEXT,
    source_id       TEXT,           -- ID in source system

    -- Community submissions
    submitted_by    TEXT,           -- optional name/handle
    submission_link TEXT,           -- original Instagram/FB post URL
    status          TEXT NOT NULL DEFAULT 'active',  -- 'active', 'pending', 'rejected'

    -- Metadata
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    is_active       BOOLEAN DEFAULT TRUE,
    quality_score   DECIMAL(3, 2),  -- 0.0–1.0

    -- Deduplication: hash of lower(title) + lower(venue_name) + date(start_time)
    fingerprint     TEXT UNIQUE
);

-- ─────────────────────────────────────────
-- INDEXES
-- ─────────────────────────────────────────

-- Geospatial index
CREATE INDEX IF NOT EXISTS events_location_idx ON events USING GIST (
    ST_SetSRID(ST_MakePoint(lng::float, lat::float), 4326)
) WHERE lat IS NOT NULL AND lng IS NOT NULL;

-- Time-based queries ("right now", "tonight")
CREATE INDEX IF NOT EXISTS events_time_idx ON events (start_time, end_time) WHERE is_active = TRUE;

-- Category filter
CREATE INDEX IF NOT EXISTS events_category_idx ON events (category, is_active);

-- Status filter (pending review queue)
CREATE INDEX IF NOT EXISTS events_status_idx ON events (status) WHERE status != 'active';

-- Source dedup
CREATE INDEX IF NOT EXISTS events_source_idx ON events (source, source_id);

-- ─────────────────────────────────────────
-- UPDATED_AT TRIGGER
-- ─────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER events_updated_at
    BEFORE UPDATE ON events
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─────────────────────────────────────────
-- ROW LEVEL SECURITY
-- ─────────────────────────────────────────

ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE venues ENABLE ROW LEVEL SECURITY;

-- Public read: only active events
CREATE POLICY "Public can read active events"
    ON events FOR SELECT
    USING (status = 'active' AND is_active = TRUE);

-- Public read: all venues
CREATE POLICY "Public can read venues"
    ON venues FOR SELECT
    USING (TRUE);

-- Public can submit events (status defaults to 'pending')
CREATE POLICY "Public can submit events"
    ON events FOR INSERT
    WITH CHECK (status = 'pending' AND source = 'community');

-- Service role has full access (pipeline uses service key, bypasses RLS)
-- No policy needed — service role bypasses RLS by default in Supabase
