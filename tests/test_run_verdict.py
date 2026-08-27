"""The nightly wrapper's verdict, exercised as the shell actually runs it.

`deploy/classify-run.sh` decides whether a run is ok, degraded, empty, error or
timeout — it is the piece that determines whether anyone is told something broke.
It was previously inline in run-scrape.sh and checked only with throwaway scripts
during development, which is the same "verified once, never again" gap FEAT-9
exists to close: a change to the pipeline's log wording, or to a regex here,
would silently restore the false green.

These tests run the real script against fixture logs rather than reimplementing
its logic in Python. A test that re-encodes the rules would agree with itself
while the shipped script drifted.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

CLASSIFY = Path(__file__).resolve().parents[1] / "deploy" / "classify-run.sh"

# The line the pipeline prints. Three numbers: events upserted, rows rejected
# during upsert, sources that failed. The verdict depends on the first and last.
SUMMARY = "Total: {events} upserted, {rows} failed, {sources} source(s) failed{names}"


def _log(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "scrape.log"
    p.write_text(body)
    return p


def classify(tmp_path: Path, body: str) -> str:
    result = subprocess.run(
        ["bash", str(CLASSIFY), str(_log(tmp_path, body))],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.mark.parametrize(
    ("events", "sources", "expected", "why"),
    [
        (18444, 0, "ok", "a healthy night"),
        (18444, 2, "degraded", "events arrived but a source is down"),
        (0, 0, "empty", "every source ran, Berlin had nothing on"),
        (0, 5, "error", "a total outage — must not read as a quiet night"),
    ],
)
def test_verdict_matrix(tmp_path, events, sources, expected, why):
    names = " (venue_website, instagram)" if sources else ""
    body = SUMMARY.format(events=events, rows=0, sources=sources, names=names) + "\n=== exit 0\n"
    assert classify(tmp_path, body) == expected, why


def test_missing_summary_is_an_error(tmp_path):
    """The run died before printing its summary. Silence is not success."""
    assert classify(tmp_path, "▶ kulturdaten\nTraceback...\n=== exit 1\n") == "error"


def test_timeout_wins_over_any_summary(tmp_path):
    """A killed run may have printed a summary before it was cut off; the kill is
    the more important fact, so it must not be reported as ok."""
    body = SUMMARY.format(events=900, rows=0, sources=0, names="") + "\n=== exit 124\n"
    assert classify(tmp_path, body) == "timeout"


def test_rejected_rows_alone_do_not_degrade_a_run(tmp_path):
    """Rows rejected during upsert and sources that died are different numbers.
    Conflating them is how "0 failed" hid dead scrapers in the first place."""
    body = SUMMARY.format(events=18444, rows=37, sources=0, names="") + "\n=== exit 0\n"
    assert classify(tmp_path, body) == "ok"


def test_the_last_summary_wins(tmp_path):
    """A log can contain an earlier partial line; only the final one is the run."""
    body = (
        SUMMARY.format(events=5, rows=0, sources=0, names="")
        + "\n"
        + SUMMARY.format(events=900, rows=0, sources=1, names=" (instagram)")
        + "\n=== exit 1\n"
    )
    assert classify(tmp_path, body) == "degraded"


def test_the_wrapper_uses_this_script_rather_than_its_own_copy(tmp_path):
    """Guards against the logic being pasted back inline, which is how it became
    untestable the first time."""
    wrapper = (CLASSIFY.parent / "run-scrape.sh").read_text()
    assert "classify-run.sh" in wrapper
    assert "notify" in wrapper
