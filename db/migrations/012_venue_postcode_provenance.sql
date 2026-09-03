-- Provenance for venue postcodes (FEAT-22 review finding 4).
--
-- A postcode read off an address and one inferred from neighbouring venues are
-- not the same fact, and downstream cannot currently tell them apart. That
-- matters because a postcode decides which Kiez an event appears in: a
-- probabilistic value may legitimately widen a search, but it must never be
-- treated as authoritative, and anyone auditing a wrong Kiez needs to know which
-- kind they are looking at.
--
-- Nullable and unconstrained on purpose: rows already carrying an address-derived
-- postcode keep a NULL source, which reads as "not inferred".

alter table venues add column if not exists postal_code_source text;
alter table venues add column if not exists postal_code_confidence real;

comment on column venues.postal_code_source is
    'How postal_code was obtained: NULL = derived from the address, '
    '''inferred_from_neighbours'' = probabilistic, see postal_code_confidence.';
comment on column venues.postal_code_confidence is
    'Share of the seven nearest venues agreeing, when the postcode was inferred.';

create index if not exists venues_postal_code_source_idx
    on venues (postal_code_source) where postal_code_source is not null;
