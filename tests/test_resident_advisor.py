"""RA scraper: genre capture (the hip-hop incident fix) and parse basics."""

from scrapers.resident_advisor import ResidentAdvisorScraper, _kebab


def _event(**overrides):
    base = {
        "id": "123",
        "title": "Test Night",
        "content": "A night of music.",
        "date": "2026-08-07",
        "startTime": "2026-08-07T22:00:00",
        "endTime": None,
        "contentUrl": "/events/123",
        "images": [],
        "venue": {"name": "Panke", "address": "Gerichtstr. 23", "area": {"name": "Wedding"}},
        "artists": [{"name": "DJ Boom Bap"}],
        "genres": [],
    }
    base.update(overrides)
    return base


def test_kebab_normalizes_ra_genre_names():
    assert _kebab("Hip-Hop") == "hip-hop"
    assert _kebab("Drum & Bass") == "drum-and-bass"
    assert _kebab("R&B") == "r-and-b"
    assert _kebab("Funk / Soul") == "funk-soul"


def test_promoter_genres_become_tags_and_source_tags():
    scraper = ResidentAdvisorScraper()
    parsed = scraper._parse_ra_event(
        _event(
            genres=[
                {"name": "Hip-Hop", "slug": "hiphop"},
                {"name": "House", "slug": "house"},
            ]
        )
    )
    assert parsed["tags"] == ["hip-hop", "house"]
    assert parsed["source_tags"] == ["hiphop", "house"]


def test_untagged_event_falls_back_to_legacy_tags():
    scraper = ResidentAdvisorScraper()
    parsed = scraper._parse_ra_event(_event(genres=[]))
    assert parsed["tags"] == ["electronic", "club"]
    assert parsed["source_tags"] == []


def test_missing_genres_field_is_tolerated():
    ev = _event()
    del ev["genres"]
    parsed = ResidentAdvisorScraper()._parse_ra_event(ev)
    assert parsed["tags"] == ["electronic", "club"]


def test_description_keeps_long_content_up_to_1500():
    long_content = "x" * 2000
    parsed = ResidentAdvisorScraper()._parse_ra_event(_event(content=long_content, artists=[]))
    assert len(parsed["description"]) == 1500
