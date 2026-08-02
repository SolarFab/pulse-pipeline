-- Product workshop M0: the demand queue. Chat searches that return NOTHING are the
-- purest signal of what users want and we lack; the discovery agent works this queue
-- first (full-loop demo: chat miss -> overnight scout -> next-day answer).

CREATE TABLE IF NOT EXISTS discovery_requests (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind         TEXT NOT NULL DEFAULT 'chat_miss',   -- chat_miss | scrape_unknown | submission
    query        TEXT,                                -- free-text the user searched
    venue        TEXT,                                -- venue filter, if any
    neighborhood TEXT,
    misses       INTEGER NOT NULL DEFAULT 1,          -- how often this gap was hit
    status       TEXT NOT NULL DEFAULT 'open',        -- open | scouted | dismissed
    first_seen   TIMESTAMPTZ DEFAULT now(),
    last_seen    TIMESTAMPTZ DEFAULT now(),
    UNIQUE NULLS NOT DISTINCT (kind, venue, query)
);

ALTER TABLE discovery_requests ENABLE ROW LEVEL SECURITY;
-- no anon policies: reads/writes go through the RPC below or service role

-- Upsert-increment via SECURITY DEFINER so the anon-key chat route can log misses
-- without any table-level write grant (and no user data is stored — only the gap).
CREATE OR REPLACE FUNCTION log_discovery_miss(
    p_query TEXT DEFAULT NULL,
    p_venue TEXT DEFAULT NULL,
    p_neighborhood TEXT DEFAULT NULL
) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    INSERT INTO discovery_requests (kind, query, venue, neighborhood)
    VALUES ('chat_miss', NULLIF(trim(p_query), ''), NULLIF(trim(p_venue), ''),
            NULLIF(trim(p_neighborhood), ''))
    ON CONFLICT (kind, venue, query) DO UPDATE
    SET misses = discovery_requests.misses + 1,
        last_seen = now(),
        status = CASE WHEN discovery_requests.status = 'dismissed'
                      THEN 'dismissed' ELSE 'open' END;
$$;

GRANT EXECUTE ON FUNCTION log_discovery_miss TO anon, authenticated;
