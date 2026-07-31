"""Regression tests for pipeline/normalizer.py.

Most cases here are translated from bugs that actually shipped (see
PROGRESS.md "Known Bugs Already Fixed") — they exist so those bugs stay dead.
"""

from datetime import UTC, datetime

from pipeline.normalizer import (
    RawEvent,
    _extract_price_cents,
    _parse_dt,
    make_fingerprint,
    normalize,
)


def utc(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


class TestParseDt:
    """Berlin wall-clock times must convert to the correct UTC instant —
    the old code hardcoded +01:00 (CET) year-round, so every summer event
    was displayed one hour late (midnight events showed as 01:00)."""

    def test_summer_naive_time_is_cest(self):
        assert _parse_dt("2026-07-15 20:00") == utc(2026, 7, 15, 18, 0)

    def test_winter_naive_time_is_cet(self):
        assert _parse_dt("2026-01-15 20:00") == utc(2026, 1, 15, 19, 0)

    def test_summer_midnight_is_berlin_midnight(self):
        # date-only input → midnight Berlin, NOT midnight UTC or CET
        assert _parse_dt("2026-07-15") == utc(2026, 7, 14, 22, 0)

    def test_t24_rolls_to_next_day_in_berlin_time(self):
        # ISO 8601 edge case: 24:00:00 = midnight at the START of the next day
        assert _parse_dt("2026-07-15T24:00:00") == utc(2026, 7, 15, 22, 0)

    def test_aware_datetime_is_converted_not_reinterpreted(self):
        assert _parse_dt("2026-07-15T20:00:00+02:00") == utc(2026, 7, 15, 18, 0)

    def test_german_date_format_is_day_first(self):
        # 03.07.2026 is July 3rd, not March 7th
        assert _parse_dt("03.07.2026 19:30") == utc(2026, 7, 3, 17, 30)

    def test_garbage_returns_none(self):
        assert _parse_dt("kein datum") is None
        assert _parse_dt(None) is None


class TestCategoryAliases:
    """Legacy/source category names must resolve to the canonical 9 —
    'market' and 'social' rows in the DB were invisible to the UI filter."""

    def make(self, category):
        return RawEvent(
            title="t",
            venue_name="v",
            source="s",
            start_time="2026-07-15",
            category=category,
        ).category

    def test_canonical_passthrough(self):
        for cat in (
            "music",
            "nightlife",
            "culture",
            "food",
            "markets",
            "workshops",
            "meetups",
            "outdoors",
            "family",
        ):
            assert self.make(cat) == cat

    def test_legacy_aliases_resolve(self):
        assert self.make("market") == "markets"
        assert self.make("social") == "meetups"
        assert self.make("entertainment") == "culture"
        assert self.make("wellness") == "outdoors"
        assert self.make("theater") == "culture"
        assert self.make("comedy") == "nightlife"
        assert self.make("yoga") == "outdoors"

    def test_case_insensitive(self):
        assert self.make("Konzert") == "music"

    def test_unknown_becomes_none(self):
        assert self.make("astrology") is None


class TestFingerprint:
    def test_stable_across_case_and_whitespace(self):
        a = make_fingerprint("Jazz Night", "Tresor", utc(2026, 7, 15, 20))
        b = make_fingerprint("  jazz night ", "Tresor", utc(2026, 7, 15, 20))
        assert a == b

    def test_venue_variants_do_not_split_events(self):
        # Same event scraped from two sources with different venue spellings
        a = make_fingerprint("Jazz Night", "Tresor", utc(2026, 7, 15, 20))
        b = make_fingerprint("Jazz Night", "Tresor / Globus", utc(2026, 7, 15, 20))
        assert a == b

    def test_different_dates_differ(self):
        a = make_fingerprint("Jazz Night", "Tresor", utc(2026, 7, 15, 20))
        b = make_fingerprint("Jazz Night", "Tresor", utc(2026, 7, 16, 20))
        assert a != b


class TestPriceCents:
    def test_free_variants(self):
        for s in ("Free", "Eintritt frei", "kostenlos", "gratis"):
            assert _extract_price_cents(s) == 0

    def test_euro_amounts(self):
        assert _extract_price_cents("€12") == 1200
        assert _extract_price_cents("ab 8€") == 800
        assert _extract_price_cents("12,50 €") == 1250

    def test_no_price(self):
        assert _extract_price_cents(None) is None
        assert _extract_price_cents("VVK") is None


class TestNormalize:
    BASE = {
        "title": "Test Event",
        "venue_name": "Test Venue",
        "source": "test",
        "start_time": "2026-07-15 20:00",
    }

    def test_valid_event_roundtrip(self):
        result = normalize({**self.BASE, "price": "Eintritt frei"})
        assert result is not None
        assert result["start_time"] == utc(2026, 7, 15, 18, 0).isoformat()
        assert result["price_cents"] == 0

    def test_missing_start_time_is_rejected(self):
        assert normalize({**self.BASE, "start_time": "???"}) is None

    def test_end_before_start_is_dropped(self):
        result = normalize({**self.BASE, "end_time": "2026-07-15 19:00"})
        assert result is not None
        assert result["end_time"] is None
