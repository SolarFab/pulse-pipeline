"""Seed integrity (unify-taxonomy §1.2): every canonical slug has labels; no drift."""

from pipeline.taxonomy import SUBCATEGORY_KEYWORDS
from scripts.seed_taxonomy import CATEGORY_LABELS, SUBCATEGORY_LABELS, build_rows


def test_every_category_and_subcategory_has_labels():
    for cat, subs in SUBCATEGORY_KEYWORDS.items():
        assert cat in CATEGORY_LABELS, f"missing label for category {cat}"
        for sub in subs:
            assert sub in SUBCATEGORY_LABELS, f"missing label for subcategory {sub}"


def test_rows_cover_all_and_only_canonical_slugs():
    rows = build_rows()
    seeded_cats = {r["category_slug"] for r in rows if r["subcategory_slug"] is None}
    assert seeded_cats == set(SUBCATEGORY_KEYWORDS) | {"sports-wellness"}
    seeded_subs = {r["subcategory_slug"] for r in rows if r["subcategory_slug"]}
    assert seeded_subs == {s for subs in SUBCATEGORY_KEYWORDS.values() for s in subs}


def test_sports_wellness_inactive_until_realignment():
    rows = build_rows()
    sw = [r for r in rows if r["category_slug"] == "sports-wellness"]
    assert sw and all(not r["is_active"] for r in sw)
    legacy = [r for r in rows if r["category_slug"] in ("family", "outdoors")]
    assert legacy and all(r["is_active"] for r in legacy)  # stay active until §4
