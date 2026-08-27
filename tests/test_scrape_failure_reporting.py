"""A source that fails must be countable.

For months `venue_website` (27 venues) and `instagram` (67 venues) produced zero
rows, and every layer reported success. Three places dropped the signal:

  1. `BaseScraper.run()` returned `0, 0` when `scrape()` raised — zero successes
     AND zero failures, indistinguishable from a quiet night.
  2. `run_all()` caught per-scraper exceptions without incrementing any counter.
  3. `main.py` ended with `os._exit(0)`, so the exit code could not carry it either.

These tests pin the property that was missing: after a source fails, something
downstream can tell. They deliberately assert on the *count*, not on log text,
because logging the failure was never the problem — nobody counted it.
"""

from __future__ import annotations

import pytest

import main
from scrapers.base import ScrapeOutcome


@pytest.fixture(autouse=True)
def _no_real_geocoder(monkeypatch):
    """run_all() ends by geocoding a tail of up to 1500 events against Nominatim
    and writing to the database. Every test in this file calls run_all, so every
    one of them would do that for real — at one request per second.

    This was invisible until the safety net was reachable: while it sat below an
    early `return` it was dead code, and these tests looked harmless. Sealing it
    here rather than per-test, because forgetting it once is a twenty-minute test
    run that silently mutates production.
    """
    calls: list[int] = []
    monkeypatch.setattr("pipeline.geocoder.run", lambda limit=0: calls.append(limit))
    return calls


class _Boom:
    """A scraper whose run() raises, as a crashing source does."""

    def run(self):
        raise RuntimeError("network is on fire")


class _Silent:
    """A scraper that fails inside scrape() — the path that returned (0, 0)."""

    def run(self):
        return ScrapeOutcome("silent", error="RuntimeError: parse failed")


class _Fine:
    def run(self):
        return ScrapeOutcome("fine", upserted=12, rows_failed=1)


class _Empty:
    """Nothing on tonight. NOT a failure, and must not be reported as one."""

    def run(self):
        return ScrapeOutcome("empty", upserted=0)


def test_outcome_separates_failure_from_emptiness():
    assert _Empty().run().crashed is False
    assert _Silent().run().crashed is True


def test_a_raising_scraper_is_counted_as_failed():
    failed = main.run_all({"boom": _Boom})
    assert failed == ["boom"]


def test_a_scraper_that_fails_inside_run_is_counted_too():
    """The (0, 0) path. It never raised, which is exactly why it was invisible."""
    failed = main.run_all({"silent": _Silent})
    assert failed == ["silent"]


def test_an_empty_source_is_not_a_failure():
    assert main.run_all({"empty": _Empty}) == []


def test_one_bad_source_does_not_stop_the_others():
    failed = main.run_all({"boom": _Boom, "fine": _Fine, "silent": _Silent})
    assert set(failed) == {"boom", "silent"}


def test_the_post_scrape_safety_net_still_runs(monkeypatch, _no_real_geocoder):
    """The regression this file did not catch the first time.

    An early version of run_all() returned above the venue-linking and geocoding
    block, making it dead code. Every test here still passed, because they all
    asserted on the return value and nothing else. A nightly run would have
    silently stopped linking venues and geocoding — and unlinked events have no
    coordinates, so they are invisible on the map.
    """
    monkeypatch.delenv("DRY_RUN", raising=False)
    main.run_all({"fine": _Fine})
    assert _no_real_geocoder, "venue linking & geocoding never ran"


def test_the_safety_net_runs_even_when_sources_failed(monkeypatch, _no_real_geocoder):
    """The events that DID arrive still need coordinates."""
    monkeypatch.delenv("DRY_RUN", raising=False)
    main.run_all({"boom": _Boom, "fine": _Fine})
    assert _no_real_geocoder, "a failed source must not skip venue linking"


def test_dry_run_skips_the_safety_net(monkeypatch, _no_real_geocoder):
    monkeypatch.setenv("DRY_RUN", "true")
    main.run_all({"fine": _Fine})
    assert not _no_real_geocoder


def test_summary_line_reports_failed_sources_separately(caplog):
    """deploy/run-scrape.sh parses this line; rows that failed to upsert and
    sources that died are different numbers and must stay different."""
    with caplog.at_level("INFO"):
        main.run_all({"fine": _Fine, "boom": _Boom})
    summary = [r.getMessage() for r in caplog.records if "Total:" in str(r.msg)]
    assert summary, "no summary line was logged"
    assert "12 upserted" in summary[-1]
    assert "1 failed" in summary[-1]  # the row rejected during upsert
    assert "1 source(s) failed" in summary[-1]  # the source that died
    assert "boom" in summary[-1]
