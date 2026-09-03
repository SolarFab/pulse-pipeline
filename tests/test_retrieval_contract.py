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
    Path(__file__).resolve().parent.parent / "db" / "migrations" / "011_retrieval_contract.sql"
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
    assert "least(greatest(p_limit, 1), 20)" in SQL


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
