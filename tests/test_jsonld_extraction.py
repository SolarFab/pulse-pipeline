"""Tests for the schema.org JSON-LD extraction layer of the generic venue
scraper — the deterministic path that avoids LLM calls entirely."""

from scrapers.venues.generic_website import GenericWebsiteScraper


def extract(html: str, url: str = "https://example.com/events"):
    scraper = GenericWebsiteScraper.__new__(GenericWebsiteScraper)  # skip __init__ (network/env)
    return scraper._extract_jsonld_events(html, url)


def wrap(jsonld: str) -> str:
    return f'<html><head><script type="application/ld+json">{jsonld}</script></head><body></body></html>'


FUTURE = "2099-08-01"


def test_extracts_event_from_graph():
    html = wrap(
        '{"@context":"https://schema.org","@graph":[{"@type":"MusicEvent",'
        f'"name":"Jazz Night","startDate":"{FUTURE}T20:00:00+02:00",'
        '"offers":{"price":"12"},"url":"/events/jazz-night",'
        '"description":"Late night jazz"}]}'
    )
    events = extract(html)
    assert len(events) == 1
    e = events[0]
    assert e["title"] == "Jazz Night"
    assert e["price"] == "€12"
    assert e["source_url"] == "https://example.com/events/jazz-night"  # made absolute


def test_event_subtypes_are_recognized():
    for t in ("Event", "MusicEvent", "TheaterEvent", "FoodEvent"):
        html = wrap(f'{{"@type":"{t}","name":"X","startDate":"{FUTURE}"}}')
        assert len(extract(html)) == 1, t


def test_past_events_are_dropped():
    html = wrap('{"@type":"Event","name":"Old","startDate":"2020-01-01T20:00:00"}')
    assert extract(html) == []


def test_incomplete_events_are_dropped():
    assert extract(wrap(f'{{"@type":"Event","startDate":"{FUTURE}"}}')) == []  # no name
    assert extract(wrap('{"@type":"Event","name":"No date"}')) == []


def test_non_event_types_are_ignored():
    html = wrap('{"@type":"Restaurant","name":"Some Bar"}')
    assert extract(html) == []


def test_top_level_list_and_offer_list():
    html = wrap(
        f'[{{"@type":"Event","name":"A","startDate":"{FUTURE}",'
        '"offers":[{"price":"8"},{"price":"15"}]}]'
    )
    events = extract(html)
    assert len(events) == 1
    assert events[0]["price"] == "€8"


def test_zero_price_is_not_labeled():
    html = wrap(f'{{"@type":"Event","name":"A","startDate":"{FUTURE}","offers":{{"price":"0"}}}}')
    assert extract(html)[0]["price"] is None


def test_malformed_json_is_skipped_not_fatal():
    html = (
        '<html><head><script type="application/ld+json">{broken json</script>'
        f'<script type="application/ld+json">{{"@type":"Event","name":"OK","startDate":"{FUTURE}"}}</script>'
        "</head><body></body></html>"
    )
    events = extract(html)
    assert len(events) == 1
    assert events[0]["title"] == "OK"
