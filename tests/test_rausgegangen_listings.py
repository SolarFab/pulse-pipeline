"""The listing layer of the rausgegangen scraper.

For months this source silently delivered a fraction of what it could. Two causes,
both invisible from the outside because the scraper still returned *some* events:

  1. It fetched four of the site's twelve categories. Comedy, exhibitions, film,
     food and sport were never requested at all — a "Comedy heute Abend?" query
     came back empty while rausgegangen's own site listed eight shows that night.
  2. It never paginated, so each category stopped after its first 32 events.

Neither failure raised anything. These tests pin the two properties that would
have: every published category is requested, and pages beyond the first are too.
The parsing itself is covered by exercising the ItemList shape the site serves.
"""

from __future__ import annotations

import json

from bs4 import BeautifulSoup

from scrapers.rausgegangen import (
    CATEGORY_HINTS,
    EDITORIAL_PAGES,
    PAGES_PER_CATEGORY,
    RausgegangeScraper,
)


def _itemlist(*slugs: str) -> str:
    """A listing page shaped like the real one: ItemList of event URLs, no Events."""
    return (
        '<html><head><script type="application/ld+json">'
        + json.dumps(
            {
                "@type": "ItemList",
                "itemListElement": [{"url": f"https://rausgegangen.de/events/{s}/"} for s in slugs],
            }
        )
        + "</script></head><body></body></html>"
    )


def test_every_published_category_is_requested():
    """The bug was omission, so assert the list, not merely that it is non-empty."""
    urls = [u for u, _ in RausgegangeScraper._listing_urls(RausgegangeScraper())]
    for slug in CATEGORY_HINTS:
        assert any(f"/kategorie/{slug}/" in u for u in urls), f"never fetched: {slug}"


def test_comedy_lives_under_shows_und_performances():
    """The category that carried every missing comedy show. Named explicitly so a
    future tidy-up of CATEGORY_HINTS cannot quietly drop it again."""
    assert "shows-und-performances" in CATEGORY_HINTS


def test_categories_are_paginated_and_editorial_pages_are_not():
    urls = [u for u, _ in RausgegangeScraper._listing_urls(RausgegangeScraper())]
    for page in range(2, PAGES_PER_CATEGORY + 1):
        assert any(f"?page={page}" in u for u in urls), f"page {page} never requested"
    for editorial in EDITORIAL_PAGES:
        assert editorial in urls
        assert f"{editorial}?page=2" not in urls


def test_collect_dedupes_across_pages_and_categories(monkeypatch):
    """Categories overlap a little and pages not at all; the same event must be
    fetched once regardless of how many listings mention it."""
    pages = {"a", "b"}

    def fake_get(self, url):
        class R:
            text = _itemlist(*sorted(pages))

        return R()

    monkeypatch.setattr(RausgegangeScraper, "get", fake_get)
    found = RausgegangeScraper().collect_event_urls()
    assert set(found) == {f"https://rausgegangen.de/events/{s}/" for s in pages}


def test_category_hint_and_source_tag_come_from_the_listing(monkeypatch):
    def fake_get(self, url):
        class R:
            text = _itemlist("some-concert") if "konzerte-und-musik" in url else _itemlist()

        return R()

    monkeypatch.setattr(RausgegangeScraper, "get", fake_get)
    found = RausgegangeScraper().collect_event_urls()
    hint, tag = found["https://rausgegangen.de/events/some-concert/"]
    assert hint == "music"
    assert tag == "rausgegangen:konzerte-und-musik"


def test_a_listing_that_yields_nothing_is_survivable(monkeypatch):
    """One dead page must not take the run down — but it also must not pass
    unnoticed, which is why collect_event_urls logs a warning for it."""

    def fake_get(self, url):
        if "party" in url:
            raise RuntimeError("boom")

        class R:
            text = _itemlist("still-here")

        return R()

    monkeypatch.setattr(RausgegangeScraper, "get", fake_get)
    found = RausgegangeScraper().collect_event_urls()
    assert "https://rausgegangen.de/events/still-here/" in found


def test_itemlist_parsing_matches_what_the_site_serves():
    soup = BeautifulSoup(_itemlist("x", "y"), "lxml")
    urls = RausgegangeScraper._extract_event_urls_from_jsonld(RausgegangeScraper(), soup)
    assert urls == [
        "https://rausgegangen.de/events/x/",
        "https://rausgegangen.de/events/y/",
    ]
