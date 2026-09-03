-- Structured, searchable location fields derived from the existing address or
-- coordinates. They remain nullable because a guessed location is worse than
-- an explicitly unknown one.
alter table public.venues
  add column if not exists postal_code text,
  add column if not exists city text,
  add column if not exists district text;

alter table public.venues
  drop constraint if exists venues_postal_code_format,
  add constraint venues_postal_code_format
    check (postal_code is null or postal_code ~ '^[0-9]{5}$') not valid;

alter table public.venues validate constraint venues_postal_code_format;

comment on column public.venues.postal_code is
  'Five-digit German postal code derived from address text or reverse geocoding.';
comment on column public.venues.city is
  'Municipality derived from address text or reverse geocoding.';
comment on column public.venues.district is
  'Administrative district (Bezirk/Kreis) derived from reverse geocoding.';

create index if not exists venues_postal_code_idx
  on public.venues (postal_code)
  where postal_code is not null;

create index if not exists venues_city_idx
  on public.venues (city)
  where city is not null;

create index if not exists venues_district_idx
  on public.venues (district)
  where district is not null;
