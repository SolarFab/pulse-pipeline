-- Retrieval contract for staged relaxation (FEAT-24, tasks 1.1/1.2/1.4/1.5/1.6/1.8, 2.x, 3.3).
--
-- Three defects this closes, all observed in production on 2-3 September 2026:
--
-- 1. An inferred subcategory was passed as a HARD filter. 45 of 97 upcoming comedy
--    events carry no subcategory, so "comedy in Prenzlauer Berg" gated the catalogue
--    down to whatever happened to be tagged. A ranking guess must not exclude.
-- 2. The caller could not test result quality: no similarity was returned, so the
--    web half could only ask "did I get rows", and three weak rows suppressed
--    relaxation while stronger events sat one constraint away.
-- 3. p_max_price_cents silently admitted rows with an unknown price, so "under 15
--    euro" could be satisfied by events whose price nobody knows.
--
-- NOT in this migration, because they belong to their own tickets:
--   dedup_key and collapse-before-LIMIT   -> FEAT-23
--   postcode/district location resolution -> FEAT-22 + FEAT-26 (geocode provenance)
-- match_events keeps today's COALESCE(event, venue) neighbourhood behaviour until
-- those land. p_area_id is accepted and validated now so FEAT-25 can build against
-- the final signature, but it resolves through the neighbourhood label for the
-- moment; the postcode tier arrives with FEAT-22.

-- ---------------------------------------------------------------------------
-- ORDERING GUARD. This migration indexes venues.postal_code and derives area
-- centroids from it, both of which FEAT-22 creates. Applied to a database
-- without that column it would fail halfway, leaving areas seeded and the RPC
-- absent. Fail at the first statement instead, with the reason.
-- ---------------------------------------------------------------------------
do $$
begin
    if not exists (
        select 1 from information_schema.columns
        where table_name = 'venues' and column_name = 'postal_code'
    ) then
        raise exception
            'venues.postal_code is missing — apply the FEAT-22 venue-location migration and its backfill before this one';
    end if;
end $$;

-- ---------------------------------------------------------------------------
-- areas: canonical location identifiers. Raw model strings must never choose a
-- SQL identifier, so the web resolver maps words -> area_id and passes the id.
-- Alias ambiguity is FEAT-25's job: raw words never reach this layer.
-- ---------------------------------------------------------------------------
create table if not exists areas (
    area_id       text primary key,
    name          text not null,
    aliases       text[] not null default '{}',
    postcodes     text[] not null default '{}',
    district      text,
    centroid_lat  double precision,
    centroid_lng  double precision
);

insert into areas (area_id, name, aliases, postcodes, district) values
  ('prenzlauer-berg','Prenzlauer Berg','{pberg,prenzlberg,"prenzl berg"}','{10405,10407,10409,10435,10437,10439}','Pankow'),
  ('kreuzberg','Kreuzberg','{x-berg,xberg,kreuzkoelln}','{10961,10963,10965,10967,10969,10997,10999}','Friedrichshain-Kreuzberg'),
  ('friedrichshain','Friedrichshain','{fhain,"f-hain"}','{10243,10245,10247,10249}','Friedrichshain-Kreuzberg'),
  ('neukoelln','Neukölln','{neukolln,nk,rixdorf}','{12043,12045,12047,12049,12051,12053,12055,12057,12059}','Neukölln'),
  ('mitte','Mitte','{"berlin mitte"}','{10115,10117,10119,10178,10179}','Mitte'),
  ('wedding','Wedding','{}','{13347,13349,13351,13353,13355,13357,13359}','Mitte'),
  ('moabit','Moabit','{}','{10551,10553,10555,10557,10559}','Mitte'),
  ('schoeneberg','Schöneberg','{schoneberg}','{10777,10779,10781,10783,10785,10787,10789,10823,10825,10827,10829}','Tempelhof-Schöneberg'),
  ('charlottenburg','Charlottenburg','{charlottenbourg}','{10585,10587,10589,10623,10625,10627,10629}','Charlottenburg-Wilmersdorf'),
  ('wilmersdorf','Wilmersdorf','{}','{10707,10709,10711,10713,10715,10717,10719}','Charlottenburg-Wilmersdorf'),
  ('lichtenberg','Lichtenberg','{}','{10315,10317,10318,10365,10367,10369}','Lichtenberg'),
  ('treptow','Treptow','{alt-treptow}','{12435,12437,12439,12487}','Treptow-Köpenick'),
  ('tempelhof','Tempelhof','{}','{12099,12101,12103,12105,12107,12109}','Tempelhof-Schöneberg'),
  ('steglitz','Steglitz','{}','{12157,12161,12163,12165,12167,12169}','Steglitz-Zehlendorf'),
  ('spandau','Spandau','{}','{13581,13583,13585,13587,13589,13591,13593,13595,13597,13599}','Spandau'),
  ('weissensee','Weißensee','{weissensee}','{13086,13088}','Pankow')
on conflict (area_id) do nothing;

-- Centroids are DERIVED from venues rather than hand-entered, so they cannot be
-- quietly wrong the way a typed coordinate can. Recomputed whenever this runs.
update areas a set
    centroid_lat = c.lat,
    centroid_lng = c.lng
from (
    select ar.area_id, avg(v.lat)::double precision as lat, avg(v.lng)::double precision as lng
    from areas ar
    join venues v on v.postal_code = any(ar.postcodes)
    where v.lat is not null
    group by ar.area_id
) c
where c.area_id = a.area_id;

-- ---------------------------------------------------------------------------
-- retrieval_config: the calibrated relevance floor and k. A table, not checked-in
-- config, because the web half deploys on its own cadence and a file would drift
-- from the deployed RPC. Exactly one row is active; readers take it in one
-- statement, so nobody observes a half-applied calibration.
-- ---------------------------------------------------------------------------
create table if not exists retrieval_config (
    id                  bigint generated always as identity primary key,
    active              boolean not null default false,
    floor               real    not null,
    k                   integer not null,
    embedding_model     text    not null,
    embedding_dim       integer not null,
    fixture_id          text    not null,
    fixture_captured_at date    not null,
    calibrated_at       timestamptz not null default now(),
    constraint retrieval_config_k_sane check (k between 1 and 20),
    constraint retrieval_config_floor_sane check (floor >= -1 and floor <= 1)
);

create unique index if not exists retrieval_config_one_active
    on retrieval_config (active) where active;

alter table retrieval_config enable row level security;
drop policy if exists retrieval_config_read on retrieval_config;
create policy retrieval_config_read on retrieval_config for select using (true);

alter table areas enable row level security;
drop policy if exists areas_read on areas;
create policy areas_read on areas for select using (true);

-- No row is seeded. An absent active record must fail CLOSED — the caller runs
-- unrelaxed and reports uncalibrated — rather than inheriting a guessed floor.

-- ---------------------------------------------------------------------------
-- Indexes for the anonymous search path.
-- ---------------------------------------------------------------------------
create index if not exists events_active_start_idx on events (start_time) where is_active;
create index if not exists venues_postal_code_idx  on venues (postal_code);

-- ---------------------------------------------------------------------------
-- match_events_v2 — a NEW function, deliberately not a replacement.
--
-- The deployed web app still calls match_events with p_category / p_subcategory /
-- p_genres. Dropping or re-signing that function lands the moment this migration
-- runs, while FEAT-25 (the web half) has not been built — so the concierge would
-- break in production and stay broken until an unrelated repo shipped. The spec's
-- "a stale caller fails loudly" is right for a developer and wrong for a user.
--
-- So v1 is left untouched and serving. FEAT-25 migrates to v2, and a later
-- migration removes v1 once nothing calls it. That ordering is the whole reason
-- this feature is two tickets in two repositories.
--   * similarity returned (1 - cosine distance); NULL when either side lacks an
--     embedding, and a NULL can never satisfy a floor.
--   * price_qualifies / price_unknown separated, so an unknown price can be
--     offered as an alternative but never counted as a match.
--   * ranking taxonomy (p_rank_*) and filtering taxonomy (p_filter_*) are
--     disjoint. The legacy combined parameters are REMOVED, not reinterpreted,
--     so a stale caller fails loudly instead of silently gating the catalogue.
--   * ordering ends at id, making it total: many events share a start_time.
--   * search_path fixed, so a mutable one cannot redirect an anonymous call.
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
    area_resolved_by text
)
language sql
stable
set search_path = public, pg_temp
as $function$
    with area as (
        -- An unknown area_id applies NO constraint. Silently filtering to nothing
        -- would be indistinguishable from "there is nothing there", which is the
        -- confusion this whole change exists to remove.
        select a.area_id, a.postcodes, a.name
        from areas a where p_area_id is not null and a.area_id = p_area_id
    ),
    base as (
        select e.*,
            coalesce(e.neighborhood, v.neighborhood) as eff_neighborhood,
            case when query_embedding is not null and e.embedding is not null
                 then 1 - (e.embedding <=> query_embedding::vector(1536)) end as sim,
            (e.price_cents is null) as p_unknown,
            (p_max_price_cents is null or (e.price_cents is not null and e.price_cents <= p_max_price_cents)) as p_ok,
            case when p_lat is not null and coalesce(e.lat, v.lat) is not null then
                6371 * acos(least(1.0,
                    cos(radians(p_lat)) * cos(radians(coalesce(e.lat, v.lat)::float8)) *
                    cos(radians(coalesce(e.lng, v.lng)::float8) - radians(p_lng)) +
                    sin(radians(p_lat)) * sin(radians(coalesce(e.lat, v.lat)::float8))))
            end as dist_km
        from events e
        left join venues v on e.venue_id = v.id
        where e.is_active
          and e.start_time >= p_date_from
          and e.start_time <= p_date_to
          -- hard filters only: explicit user selection
          and (p_filter_category    is null or e.category = p_filter_category)
          and (p_filter_subcategory is null or e.subcategory = p_filter_subcategory)
          and (p_neighborhood is null
               or coalesce(e.neighborhood, v.neighborhood) ilike '%' || p_neighborhood || '%')
          and (p_venue is null or e.venue_name ilike '%' || p_venue || '%')
          and (not p_family  or e.family_friendly)
          and (not p_outdoor or e.outdoor)
          and (not p_free    or e.free_entry)
          -- unknown price is ELIGIBLE but flagged; the caller decides whether it counts
          and (p_max_price_cents is null or e.price_cents is null or e.price_cents <= p_max_price_cents)
          and (p_area_id is null
               or not exists (select 1 from area)
               or coalesce(e.neighborhood, v.neighborhood) ilike '%' || (select name from area) || '%')
    )
    select b.id, b.title, b.venue_name, b.start_time, b.category, b.subcategory,
           b.price, b.eff_neighborhood, b.genres, b.dist_km,
           b.sim, b.p_ok, b.p_unknown,
           case when p_area_id is null then null
                when not exists (select 1 from area) then 'area_unknown'
                else 'neighborhood_label' end
    from base b
    where (p_lat is null or (b.dist_km is not null and b.dist_km <= p_radius_km))
    order by
        -- 1. exact title match
        case when p_query_text is not null and length(p_query_text) >= 4
                  and b.title ilike '%' || p_query_text || '%' then 0 else 1 end,
        -- 2. taxonomy AGREEMENT: ranks, never excludes. NULL is a non-match.
        case when p_rank_subcategory is not null and b.subcategory = p_rank_subcategory then 0
             when p_rank_category    is not null and b.category    = p_rank_category    then 1
             when p_rank_genres      is not null and b.genres && p_rank_genres           then 2
             else 3 end,
        -- 3. similarity, best first, unscored last
        b.sim desc nulls last,
        -- 4. distance when a location was asked for
        case when p_lat is not null then b.dist_km end asc nulls last,
        -- 5. soonest
        b.start_time asc,
        -- 6. id: the unique tie-break that makes the ordering total
        b.id asc
    limit least(greatest(p_limit, 1), 20)
$function$;
