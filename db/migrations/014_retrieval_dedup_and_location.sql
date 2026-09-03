-- Phase 6 review fixes for FEAT-24 (findings 1 and 3).
--
-- 1. dedup_key and collapse-before-LIMIT. FEAT-23 is no longer a launch
--    prerequisite, so this protection has to live here: without it three copies
--    of one event satisfy a sufficiency check that one event would not, and they
--    consume the SQL limit so the real alternatives never surface. 23% of
--    upcoming rows are duplicates and 1,134 groups disagree on subcategory, so
--    which copy a filter happens to match decides whether an event is findable.
--
-- 3. Location resolution in the accepted order — postcode, district, label,
--    centroid radius — and EVENT-FIRST within each tier.
--
--    FEAT-22 gives structured location to venues only. Events have no postcode
--    column, so a venue-first lookup would relabel every event that knows better:
--    654 of The Makery's 763 upcoming events carry coordinates that differ from
--    their venue row, because the organiser roves and the venue row is its own
--    studio. The event's postcode is therefore derived inline from its address
--    and wins over the venue's.

-- ---------------------------------------------------------------------------
-- Dedup key. Normalisation is deliberately aggressive on punctuation and
-- whitespace, because that is exactly how the duplicates differ:
--     "Tati Comedy _ Die Stand Up Comedy Show"
--     "Tati Comedy  - Die Stand Up Comedy Show"
--     "Tati Comedy - Die Stand Up Comedy Show"
-- Same show, same venue, same minute, three rows and three different fingerprints.
--
-- start_time is included at MINUTE precision, not date: two showings of one play
-- on one day are different events and must both survive. Rounding to the day
-- would silently merge them — the opposite defect, and a worse one, because a
-- lost event leaves no trace.
-- ---------------------------------------------------------------------------
-- ASCII fold. German umlauts expand to TWO letters — ue, not u — because that is
-- how the other spelling actually appears: sources write "Bühnen Rausch" and
-- "Buehnen Rausch" for the same venue. translate() is one-to-one and cannot do
-- that, so the umlauts are replaced first and translate only handles accents.
create or replace function unaccent_safe(t text) returns text
language sql immutable
set search_path = public, pg_temp
as $$
    select translate(
        replace(replace(replace(replace(replace(replace(replace(
            coalesce(t, ''),
            'ä', 'ae'), 'ö', 'oe'), 'ü', 'ue'),
            'Ä', 'Ae'), 'Ö', 'Oe'), 'Ü', 'Ue'), 'ß', 'ss'),
        'éèêëáàâíìîóòôúùû', 'eeeeaaaiiiooouuu');
$$;

create or replace function event_dedup_key(
    p_title text, p_venue text, p_start timestamptz
) returns text
language sql immutable
set search_path = public, pg_temp
as $$
    select encode(sha256(convert_to(
        coalesce(regexp_replace(lower(unaccent_safe(p_title)), '[^a-z0-9]+', '', 'g'), '') || '|' ||
        coalesce(regexp_replace(lower(unaccent_safe(p_venue)), '[^a-z0-9]+', '', 'g'), '') || '|' ||
        to_char(date_trunc('minute', p_start at time zone 'UTC'), 'YYYY-MM-DD"T"HH24:MI'),
        'UTF8'), 'sha256'), 'hex');
$$;

create index if not exists events_dedup_key_idx
    on events (event_dedup_key(title, venue_name, start_time));

-- ---------------------------------------------------------------------------
-- match_events_v2, revised: dedup before LIMIT, and the full location ladder.
-- ---------------------------------------------------------------------------
create or replace function match_events_v2(
    query_embedding    text     default null,
    p_query_text       text     default null,
    p_rank_category    text     default null,
    p_rank_subcategory text     default null,
    p_rank_genres      text[]   default null,
    p_filter_category  text     default null,
    p_filter_subcategory text   default null,
    p_area_id          text     default null,
    p_date_from        timestamptz default now(),
    p_date_to          timestamptz default (now() + interval '14 days'),
    p_neighborhood     text     default null,
    p_venue            text     default null,
    p_family           boolean  default false,
    p_outdoor          boolean  default false,
    p_free             boolean  default false,
    p_max_price_cents  integer  default null,
    p_lat              double precision default null,
    p_lng              double precision default null,
    p_radius_km        double precision default 1.5,
    p_limit            integer  default 10
)
returns table (
    id uuid, title text, venue_name text, start_time timestamptz,
    category text, subcategory text, price text, neighborhood text,
    genres text[], distance_km double precision,
    similarity double precision,
    price_qualifies boolean, price_unknown boolean,
    area_resolved_by text, dedup_key text
)
language sql
stable
set search_path = public, pg_temp
as $function$
    with area as (
        select a.area_id, a.postcodes, a.name, a.district,
               a.centroid_lat, a.centroid_lng
        from areas a where p_area_id is not null and a.area_id = p_area_id
    ),
    base as (
        select e.*,
            coalesce(e.neighborhood, v.neighborhood) as eff_neighborhood,
            -- EVENT-FIRST at every tier. The event's own address decides; the
            -- venue only fills a gap.
            coalesce(substring(e.address from '\m1[0-9]{4}\M'), v.postal_code) as eff_postcode,
            v.district as eff_district,
            event_dedup_key(e.title, e.venue_name, e.start_time) as dkey,
            case when query_embedding is not null and e.embedding is not null
                 then 1 - (e.embedding <=> query_embedding::vector(1536)) end as sim,
            (e.price_cents is null) as p_unknown,
            (p_max_price_cents is null or (e.price_cents is not null and e.price_cents <= p_max_price_cents)) as p_ok,
            case when coalesce(p_lat, (select centroid_lat from area)) is not null
                      and coalesce(e.lat, v.lat) is not null then
                6371 * acos(least(1.0,
                    cos(radians(coalesce(p_lat, (select centroid_lat from area)))) * cos(radians(coalesce(e.lat, v.lat)::float8)) *
                    cos(radians(coalesce(e.lng, v.lng)::float8) - radians(coalesce(p_lng, (select centroid_lng from area)))) +
                    sin(radians(coalesce(p_lat, (select centroid_lat from area)))) * sin(radians(coalesce(e.lat, v.lat)::float8))))
            end as dist_km
        from events e
        left join venues v on e.venue_id = v.id
        where e.is_active
          and e.start_time >= p_date_from
          and e.start_time <= p_date_to
          and (p_filter_category    is null or e.category = p_filter_category)
          and (p_filter_subcategory is null or e.subcategory = p_filter_subcategory)
          and (p_neighborhood is null
               or coalesce(e.neighborhood, v.neighborhood) ilike '%' || p_neighborhood || '%')
          and (p_venue is null or e.venue_name ilike '%' || p_venue || '%')
          and (not p_family  or e.family_friendly)
          and (not p_outdoor or e.outdoor)
          and (not p_free    or e.free_entry)
          and (p_max_price_cents is null or e.price_cents is null or e.price_cents <= p_max_price_cents)
    ),
    -- The tier that answers is decided ONCE for the whole query, not per row:
    -- a mixed result set would make "which source answered" meaningless.
    tier as (
        select case
            when p_area_id is null then null
            when not exists (select 1 from area) then 'area_unknown'
            when exists (select 1 from base b where b.eff_postcode = any((select postcodes from area))) then 'postcode'
            when exists (select 1 from base b where b.eff_district = (select district from area)) then 'district'
            when exists (select 1 from base b where b.eff_neighborhood ilike '%' || (select name from area) || '%') then 'neighborhood_label'
            when (select centroid_lat from area) is not null then 'centroid_radius'
            else 'area_unmatched' end as src
    ),
    located as (
        select b.* from base b, tier t
        where p_area_id is null
           or t.src in ('area_unknown', 'area_unmatched')
           or (t.src = 'postcode'           and b.eff_postcode = any((select postcodes from area)))
           or (t.src = 'district'           and b.eff_district = (select district from area))
           or (t.src = 'neighborhood_label' and b.eff_neighborhood ilike '%' || (select name from area) || '%')
           or (t.src = 'centroid_radius'    and b.dist_km is not null and b.dist_km <= greatest(p_radius_km, 3))
    ),
    -- Collapse BEFORE the limit. Ranking inside the group is the same comparator
    -- chain, so the surviving copy is the best-tagged one deterministically —
    -- 1,134 duplicate groups disagree about subcategory, so which copy wins
    -- decides whether the event is findable at all.
    deduped as (
        select *, row_number() over (
            partition by dkey
            order by
                case when subcategory is not null then 0 else 1 end,
                case when genres is not null and cardinality(genres) > 0 then 0 else 1 end,
                sim desc nulls last,
                id asc
        ) as rn
        from located
        where (p_lat is null or (dist_km is not null and dist_km <= p_radius_km))
    )
    select d.id, d.title, d.venue_name, d.start_time, d.category, d.subcategory,
           d.price, d.eff_neighborhood, d.genres, d.dist_km,
           d.sim, d.p_ok, d.p_unknown, (select src from tier), d.dkey
    from deduped d
    where d.rn = 1
    order by
        case when p_query_text is not null and length(p_query_text) >= 4
                  and d.title ilike '%' || p_query_text || '%' then 0 else 1 end,
        case when p_rank_subcategory is not null and d.subcategory = p_rank_subcategory then 0
             when p_rank_category    is not null and d.category    = p_rank_category    then 1
             when p_rank_genres      is not null and d.genres && p_rank_genres           then 2
             else 3 end,
        d.sim desc nulls last,
        case when p_lat is not null or p_area_id is not null then d.dist_km end asc nulls last,
        d.start_time asc,
        d.id asc
    limit least(greatest(p_limit, 1), 20)
$function$;

-- ---------------------------------------------------------------------------
-- Atomic config replacement (FEAT-24 review finding 2).
--
-- The calibrator did this as two REST calls — deactivate, then insert — and
-- called it atomic in a comment. It is not: a failure between them leaves NO
-- active row, and FEAT-25 then treats the system as uncalibrated and stops
-- widening entirely. The failure is silent and looks like normal fail-closed
-- behaviour, which is the worst kind.
--
-- One function, one transaction. Either the new row is active or the old one
-- still is; there is no moment with neither.
-- ---------------------------------------------------------------------------
create or replace function set_active_retrieval_config(
    p_floor real, p_k integer, p_embedding_model text, p_embedding_dim integer,
    p_fixture_id text, p_fixture_captured_at date
) returns bigint
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    new_id bigint;
begin
    update retrieval_config set active = false where active;
    insert into retrieval_config (
        active, floor, k, embedding_model, embedding_dim, fixture_id, fixture_captured_at
    ) values (
        true, p_floor, p_k, p_embedding_model, p_embedding_dim, p_fixture_id, p_fixture_captured_at
    ) returning id into new_id;
    return new_id;
end $$;

revoke all on function set_active_retrieval_config(real, integer, text, integer, text, date) from public, anon;
grant execute on function set_active_retrieval_config(real, integer, text, integer, text, date)
    to service_role;
