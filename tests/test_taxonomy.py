"""Taxonomy consistency tests.

The UI filter (web/src/lib/types.ts) only understands canonical
(category, subcategory) pairs — anything else in the DB is invisible to
filtering. These tests keep the pipeline's enforcement airtight.
"""

from pipeline.categorizer import (
    CATEGORIES,
    SUBCATEGORIES,
    SUBCATEGORY_PARENT,
    SUBCATEGORY_SYNONYMS,
    normalize_subcategory,
)
from pipeline.normalizer import VALID_CATEGORIES


def test_categorizer_and_normalizer_agree_on_categories():
    assert set(CATEGORIES) == VALID_CATEGORIES


def test_every_synonym_maps_to_a_canonical_subcategory():
    for source, target in SUBCATEGORY_SYNONYMS.items():
        assert target in SUBCATEGORY_PARENT, f"synonym {source!r} -> {target!r} is not canonical"


def test_subcategory_parent_covers_all_subcategories():
    for cat, subs in SUBCATEGORIES.items():
        for sub in subs:
            assert SUBCATEGORY_PARENT[sub] == cat


class TestNormalizeSubcategory:
    def test_canonical_passthrough(self):
        assert normalize_subcategory("music", "jazz-blues") == "jazz-blues"

    def test_synonym_resolves(self):
        assert normalize_subcategory("music", "jazz") == "jazz-blues"
        assert normalize_subcategory("nightlife", "DJ set") == "club-night"
        assert normalize_subcategory("markets", "Flohmarkt") == "flea-market"

    def test_case_and_whitespace_insensitive(self):
        assert normalize_subcategory("music", "  Jazz ") == "jazz-blues"

    def test_wrong_category_pair_is_rejected(self):
        # 'party' is canonical — but under nightlife, not culture. Storing the
        # mismatched pair would make the event invisible to the subtag filter.
        assert normalize_subcategory("culture", "party") is None
        assert normalize_subcategory("culture", "jazz") is None

    def test_unknown_value_is_rejected_not_stored(self):
        assert normalize_subcategory("music", "indie-psych / krautrock") is None

    def test_empty_input(self):
        assert normalize_subcategory("music", None) is None
        assert normalize_subcategory("music", "") is None
        assert normalize_subcategory(None, "jazz") is None
