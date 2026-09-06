"""The retrieval contract migration, asserted as SQL text.

These do not need a database: they pin the properties that a review or a later
edit could silently undo, and every one of them corresponds to a defect observed
in production on 2-3 September 2026.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SQL = (
    Path(__file__).resolve().parent.parent / "db" / "migrations" / "013_retrieval_contract.sql"
).read_text()


def test_v1_is_not_dropped_or_resigned():
    """The deployed web app still calls match_events v1. Removing it here would
    break the live concierge until an unrelated repo shipped FEAT-25."""
    assert "drop function if exists match_events(" not in SQL
    assert "create or replace function match_events_v2(" in SQL


def test_ranking_taxonomy_never_appears_in_a_where_clause():
    """The original defect: an inferred subcategory used as a hard gate, against a
    field 45 of 97 comedy events do not carry."""
    where_block = SQL.split("where e.is_active")[1].split("order by")[0]
    for param in ("p_rank_category", "p_rank_subcategory", "p_rank_genres"):
        assert param not in where_block, f"{param} must rank, never filter"


def test_filter_taxonomy_is_applied_as_a_hard_filter():
    where_block = SQL.split("where e.is_active")[1].split("order by")[0]
    assert "p_filter_category" in where_block
    assert "p_filter_subcategory" in where_block


def test_ranking_taxonomy_is_used_in_the_order_by():
    order_block = SQL.split("order by")[1]
    assert "p_rank_subcategory" in order_block
    assert "p_rank_category" in order_block
    assert "p_rank_genres" in order_block


def test_ordering_ends_at_id_so_it_is_total():
    """start_time is not unique — 1,095 title/date pairs share one. Without a
    unique final tier, 'identical input gives identical order' is untestable."""
    order_block = SQL.split("order by")[1]
    assert "b.id asc" in order_block
    assert order_block.index("b.id asc") > order_block.index("b.start_time asc")


def test_similarity_is_one_minus_cosine_distance():
    """pgvector's <=> is DISTANCE. Returning it raw would invert the threshold."""
    assert "1 - (e.embedding <=> query_embedding::vector(1536))" in SQL


def test_similarity_is_null_when_either_side_lacks_an_embedding():
    assert "query_embedding is not null and e.embedding is not null" in SQL


def test_price_qualifies_requires_a_known_price():
    """Unknown price may be offered as an alternative but can never satisfy
    'under 15 euro' — otherwise unknown values manufacture sufficiency."""
    m = re.search(
        r"\(p_max_price_cents is null or \(e\.price_cents is not null[^)]*\)\) as p_ok", SQL
    )
    assert m, "price_qualifies must require price_cents IS NOT NULL"


def test_price_unknown_is_reported_separately():
    assert "(e.price_cents is null) as p_unknown" in SQL


def test_unknown_area_applies_no_constraint():
    """Silently filtering to nothing is indistinguishable from 'there is nothing
    there' — the exact confusion this change exists to remove."""
    assert "not exists (select 1 from area)" in SQL
    assert "area_unknown" in SQL


def test_search_path_is_fixed_on_the_anonymous_function():
    assert "set search_path = public, pg_temp" in SQL


def test_limit_stays_bounded():
    assert "least(greatest(p_limit, 1), 200)" in SQL12


def test_exactly_one_active_config_row_is_enforced():
    assert "create unique index if not exists retrieval_config_one_active" in SQL
    assert "on retrieval_config (active) where active" in SQL


def test_no_config_row_is_seeded_so_it_fails_closed():
    """An absent active record must make the caller run unrelaxed and report
    uncalibrated, not inherit a guessed floor."""
    assert "insert into retrieval_config" not in SQL


def test_area_centroids_are_derived_from_venues_not_typed():
    """A hand-entered coordinate can be quietly wrong; a derived one cannot."""
    assert "update areas a set" in SQL
    assert "avg(v.lat)" in SQL


@pytest.mark.parametrize("area", ["prenzlauer-berg", "neukoelln", "kreuzberg", "mitte"])
def test_the_areas_in_the_reported_bugs_are_seeded(area):
    assert f"'{area}'" in SQL


def test_prenzlauer_berg_carries_its_real_postcodes():
    assert "{10405,10407,10409,10435,10437,10439}" in SQL


def test_neukoelln_covers_reuterstrasse():
    """Reuterstraße 82 is 12053 — the workshop Fabian saw mis-attributed."""
    assert "12053" in SQL


def test_indexes_for_the_anonymous_path_exist():
    assert "events_active_start_idx" in SQL
    assert "venues_postal_code_idx" in SQL


def test_dedup_and_location_tiers_are_left_to_their_own_tickets():
    """FEAT-23 owns dedup; FEAT-22/26 own postcode resolution. Implementing them
    here would duplicate work in flight and contradict the agreed ownership."""
    # The comment block names them as other tickets' work; the CONTRACT must not.
    returns_block = SQL.split("returns table (")[1].split(")\nlanguage sql")[0]
    assert "dedup_key" not in returns_block
    assert "postcode" not in returns_block
    assert "postcodes" in SQL  # the areas table is seeded, ready for FEAT-22


# --- Review findings 1 and 3: dedup and the location ladder --------------------

SQL12 = (
    Path(__file__).resolve().parent.parent
    / "db"
    / "migrations"
    / "014_retrieval_dedup_and_location.sql"
).read_text()


def test_helper_is_defined_before_the_function_that_calls_it():
    """Postgres validates a SQL function body at creation, so a forward reference
    fails the migration rather than deferring."""
    assert SQL12.index("function unaccent_safe") < SQL12.index("function event_dedup_key")


def test_dedup_key_normalises_the_punctuation_that_actually_differs():
    """The three Tati Comedy rows differ only by `_`, `-` and a double space."""
    assert "'[^a-z0-9]+', '', 'g'" in SQL12
    assert "lower(unaccent_safe" in SQL12


def test_dedup_key_keeps_minute_precision():
    """Rounding to the day would merge two showings of one play into one row —
    the opposite defect, and worse: a lost event leaves no trace."""
    assert "date_trunc('minute'" in SQL12
    assert "date_trunc('day'" not in SQL12


def test_duplicates_collapse_before_the_limit():
    dedup_at = SQL12.index("row_number() over (")
    limit_at = SQL12.rindex("limit least(greatest(p_limit")
    assert dedup_at < limit_at, "dedup must precede LIMIT or copies consume the limit"


def test_the_surviving_copy_is_chosen_deterministically():
    """1,134 duplicate groups disagree about subcategory, so which copy wins
    decides whether the event is findable at all."""
    window = SQL12.split("row_number() over (")[1].split(") as rn")[0]
    assert "subcategory is not null then 0" in window
    assert "id asc" in window, "must end in a unique tie-break"


def test_location_is_event_first_at_the_postcode_tier():
    """654 of The Makery's 763 upcoming events know their location better than
    their venue row does. Venue-first would relabel every one."""
    assert "coalesce(substring(e.address from '\\m1[0-9]{4}\\M'), v.postal_code)" in SQL12


def test_dedup_key_is_indexed():
    assert "events_dedup_key_idx" in SQL12


def test_both_helpers_fix_their_search_path():
    for fn in SQL12.split("create or replace function")[1:]:
        assert "set search_path = public, pg_temp" in fn.split("as $")[0]


def test_migration_013_refuses_to_run_before_feat_22():
    """013 indexes venues.postal_code and derives centroids from it, both created
    by FEAT-22. Without the guard it would fail halfway, leaving areas seeded and
    the RPC absent."""
    assert "information_schema.columns" in SQL
    assert "raise exception" in SQL
    guard_at = SQL.index("raise exception")
    assert guard_at < SQL.index("insert into areas"), "the guard must precede any write"


def test_umlauts_fold_to_two_letters_not_one():
    """Sources write both 'Bühnen Rausch' and 'Buehnen Rausch'. translate() is
    one-to-one and maps ü->u, which does not equate them; replace() does."""
    assert "'ü', 'ue'" in SQL12
    assert "'ö', 'oe'" in SQL12
    assert "'ß', 'ss'" in SQL12


def test_the_config_swap_is_one_transaction():
    """Two REST calls leave a window with no active row if the second fails, and
    FEAT-25 then reads the system as uncalibrated and silently stops widening."""
    assert "create or replace function set_active_retrieval_config" in SQL12
    fn = SQL12.split("set_active_retrieval_config")[1]
    assert "update retrieval_config set active = false" in fn
    assert "insert into retrieval_config" in fn
    assert fn.index("update retrieval_config") < fn.index("insert into retrieval_config")


def test_the_config_writer_is_not_public():
    assert "revoke all on function set_active_retrieval_config" in SQL12
    assert "to service_role" in SQL12


def test_the_matched_tier_ranks_rather_than_filters():
    order_block = SQL12.split("order by")[-1]
    assert "d.loc_src when 'postcode' then 0" in order_block
    assert order_block.index("loc_src") < order_block.index("d.sim desc")


def test_tier_strength_orders_results():
    """Postcode evidence outranks a label, but a label match is returned."""
    order_block = SQL12.split("order by")[-1]
    for tier, rank in [
        ("postcode", "0"),
        ("district", "1"),
        ("neighborhood_label", "2"),
        ("centroid_radius", "3"),
    ]:
        assert f"'{tier}' then {rank}" in order_block


def test_area_annotates_and_never_filters():
    """Retrieve wide, rank in code, show narrow. With a date window the candidate
    set is ~400 rows; every exclusion here was a way to lose Cosmic Comedy."""
    located = SQL12.split("located as (")[1].split("),")[0]
    assert "loc_src" in located
    assert "where" not in located.lower(), "location must annotate, not exclude"
    for tier in ["postcode", "district", "neighborhood_label", "centroid_radius"]:
        assert f"'{tier}'" in located


def test_retrieval_breadth_is_sized_from_measurement():
    """Latency is flat in the limit (~474 bytes/row, scan paid regardless), so a
    low cap only discards work already done. Default 100, ceiling 200."""
    assert "p_limit            integer  default 100" in SQL12
    assert "least(greatest(p_limit, 1), 200)" in SQL12


def test_dedup_key_uses_the_builtin_one_argument_sha256():
    """sha256(bytea) takes one argument; the 'sha256' string belongs to pgcrypto's
    digest(). The two-argument form fails at apply time with 42883 — caught
    only when the migration was actually applied, not by any text test."""
    assert "sha256(convert_to(" in SQL12
    assert "'UTF8'), 'sha256')" not in SQL12
