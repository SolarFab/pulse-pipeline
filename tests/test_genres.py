"""Genre vocabulary + detector (genre-dimension §2.7).

The detector is the layer that recovers genre from prose — 6 of the 9 hip-hop
events in the incident week had their genre only in the description. Precision
matters more than recall: a wrong genre poisons a filter users trust.
"""

import pytest

from pipeline.genres import (
    FORMAT_WORDS,
    GENRE_GROUPS,
    GENRE_SLUGS,
    alias_map,
    canonicalize,
    detect_genres,
    genre_rows,
    merge_genres,
)

# ── vocabulary integrity ─────────────────────────────────────────────────────


def test_no_format_words_in_vocabulary():
    """Rule 1: RA ships 'Club' as a genre and NOCTAVA ships 'Live Music'.
    Those are formats — the exact conflation this dimension exists to escape."""
    assert not (GENRE_SLUGS & FORMAT_WORDS)


def test_every_genre_belongs_to_a_known_group():
    for row in genre_rows():
        if row["kind"] == "genre":
            assert row["parent"] in GENRE_GROUPS, row["category_slug"]


def test_rows_are_unique_per_kind_and_slug():
    rows = genre_rows()
    keys = [(r["kind"], r["category_slug"]) for r in rows]
    assert len(keys) == len(set(keys))


def test_ra_vocabulary_is_covered():
    """RA's promoter tags are our highest-quality genre source — every one of
    them (minus the format leak) must resolve to a canonical slug."""
    import json
    from pathlib import Path

    ra = json.loads(
        (Path(__file__).resolve().parent.parent / "data" / "ra_genres.json").read_text()
    )
    aliases = alias_map()
    unresolved = [
        g["name"]
        for g in ra["data"]["genres"]
        if g["name"].lower() not in aliases
        and g["name"].lower().replace("-", " ") not in aliases
        and g["name"].lower() not in FORMAT_WORDS
    ]
    assert unresolved == [], f"RA genres with no canonical mapping: {unresolved}"


# ── alias mapping ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Hip Hop / Rap", "hip-hop"),  # Eventbrite
        ("hiphop", "hip-hop"),  # RA slug
        ("rap", "hip-hop"),
        ("R&B", "r-and-b"),
        ("rnb", "r-and-b"),
        ("EDM / Electronic", "electronic"),
        ("Klassik", "classical"),
        ("Schlager & Volksmusik", "schlager"),
    ],
)
def test_source_vocabularies_canonicalize(raw, expected):
    assert canonicalize([raw]) == [expected]


def test_unknown_values_are_dropped_not_invented():
    assert canonicalize(["Sonstiges", "attraction.category.Police", ""]) == []


# ── detection ────────────────────────────────────────────────────────────────


def test_detects_genre_from_german_description():
    """The Best Mistake case: genre lives only in the description."""
    event = {
        "title": "Best Mistake @ Kitty Cheng",
        "category": "nightlife",
        "description": "Jeden Donnerstag bringt BEST MISTAKE DJs, die Hip-Hop, RnB und Trap mischen.",
    }
    found = detect_genres(event)
    assert "hip-hop" in found
    assert "r-and-b" in found
    assert "trap" in found


def test_detects_from_source_tags_before_text():
    event = {"title": "Untitled", "description": "", "source_tags": ["hiphop", "house"]}
    assert detect_genres(event) == ["hip-hop", "house"]


def test_no_signal_no_tag():
    """Absence beats a wrong guess — the facets.py discipline."""
    event = {
        "title": "Offene Malstunde in der Bibliothek",
        "category": "culture",
        "description": "Kommen Sie vorbei und malen Sie mit uns.",
    }
    assert detect_genres(event) == []


def test_text_detection_is_gated_to_music_ish_categories():
    """A senior meetup listing "klassische Musik" among its afternoon
    activities is a keyword match, not a classical concert."""
    senior = {
        "title": "Fröhliche Senioren gesucht!",
        "category": "meetups",
        "description": "Programm: Lesungen, Reiseberichte, klassische Musik, Tanzmusik.",
    }
    assert detect_genres(senior) == []
    # ...but an explicit source assertion still counts, in any category.
    senior_tagged = {**senior, "source_tags": ["Klassik"]}
    assert detect_genres(senior_tagged) == ["classical"]


@pytest.mark.parametrize(
    "title",
    [
        "Pop-up Store Eröffnung",  # 'pop' must not match pop-up
        "Bauhaus Ausstellung",  # 'house' must not match Bauhaus
        "Rockabilly Tanzkurs für Anfänger",  # 'rock' must not match Rockabilly
        "Diskothek Revival",  # 'disco' must not match Diskothek
        "Funktionale Programmierung",  # 'funk' must not match Funktionale
    ],
)
def test_german_false_positives_are_avoided(title):
    assert detect_genres({"title": title, "description": "", "category": "culture"}) == []


def test_detection_is_idempotent():
    event = {
        "title": "Techno Nacht",
        "category": "nightlife",
        "description": "Techno all night",
        "genres": ["techno"],
    }
    once = merge_genres(event)
    event["genres"] = once
    assert merge_genres(event) == once


def test_merge_writes_only_canonical_genres():
    """The dimension is separate from `tags` on purpose: an audit found 955
    events tagged `singer-songwriter` and 241 `classical` by the old free-text
    categorizer. Legacy topic tags must never leak into the genre filter."""
    event = {
        "title": "Hip-Hop Jam",
        "category": "music",
        "description": "",
        "tags": ["free", "outdoor", "singer-songwriter"],
    }
    assert merge_genres(event) == ["hip-hop"]


def test_merge_drops_non_vocabulary_values_already_stored():
    event = {"title": "x", "description": "", "genres": ["not-a-genre", "techno"]}
    assert merge_genres(event) == ["techno"]
