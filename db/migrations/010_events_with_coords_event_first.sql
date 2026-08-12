-- events_with_coords: the EVENT's own location wins; the venue only fills gaps.
--
-- The view coalesced VENUE first, so a venue row overruled every event that knew
-- better. That put all 287 upcoming The Makery workshops on the marketplace's head
-- office in Prenzlauer Berg, even after each event had been given its partner
-- studio's real coordinates (scripts/backfill_makery_addresses.py).
--
-- Checked before flipping, because the reverse was plausible: where event and venue
-- disagree by more than 1 km, WHICH side is right? Every case examined had a stale
-- venue row and a correct event:
--     Badehaus Berlin     event 52.507,13.455 (Revaler Str.) | venue 52.632,13.507
--     Klunkerkranich      event 52.482,13.432 (Nk Arcaden)   | venue 52.508,13.529
--     Lokschuppen Berlin  event 52.507,13.451 (Revaler Str.) | venue 52.537,13.342
-- Venue coordinates are older and derived from a name; event coordinates come from
-- the event's own address. So event-first is not a trade — it is better on both
-- sides of the disagreement.
--
-- This also makes the view agree with match_events (migration 009). Two access
-- paths resolving the same event to two different places is the bug class that
-- started all of this.
--
-- venues.lat is NOT NULL, so clearing the marketplace's coordinate was not an
-- option; the coalesce order is where this has to be fixed.
--
-- Measured after: Makery events render on 107 distinct pins instead of 1, and
-- 289 of 22,182 upcoming events (1.3%) still have no coordinate from either side.

CREATE OR REPLACE VIEW events_with_coords AS
 SELECT e.id, e.title, e.venue_name, e.venue_id,
    COALESCE(e.lat, v.lat) AS lat, COALESCE(e.lng, v.lng) AS lng,
    COALESCE(e.neighborhood, v.neighborhood) AS neighborhood,
    COALESCE(e.address, v.address) AS address,
    e.start_time, e.end_time, e.category, e.subcategory, e.tags, e.description,
    e.price, e.price_cents, e.image_url, e.source, e.source_url, e.source_id,
    e.source_tags, e.submitted_by, e.submission_link, e.status, e.fingerprint,
    e.quality_score, e.is_active, e.created_at, e.updated_at, e.genres
   FROM events e LEFT JOIN venues v ON e.venue_id = v.id;

GRANT SELECT ON events_with_coords TO anon, authenticated;
