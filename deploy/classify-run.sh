#!/usr/bin/env bash
# Read a scrape log, print one word: ok | degraded | empty | error | timeout
#
# This is the production consumer of the pipeline's summary line, and the thing
# that decides whether a nightly run is worth waking someone for. It lives in its
# own file so it can be tested — see tests/test_run_verdict.py. It was previously
# inline in run-scrape.sh and verified only by throwaway scripts, which is the
# same "checked once, never again" gap that FEAT-9 exists to close: a change to
# the log wording or to a regex here would silently restore the false green.
#
# The line it parses:
#
#   Total: 18444 upserted, 1 failed, 2 source(s) failed (venue_website, instagram)
#          ^^^^^ events     ^ rows     ^ sources
#
# "rows" are individual events rejected during upsert; "sources" are scrapers
# that died. They are different numbers and the verdict depends on both.
set -uo pipefail

LOG="${1:?usage: classify-run.sh <logfile>}"

RESULT="$(grep -E 'Total: [0-9]+ upserted' "$LOG" | tail -1)"
UPSERTED="$(printf '%s' "$RESULT" | sed -nE 's/.*Total: ([0-9]+) upserted.*/\1/p')"
BAD_SOURCES="$(printf '%s' "$RESULT" | sed -nE 's/.*, ([0-9]+) source\(s\) failed.*/\1/p')"
TIMED_OUT="$(grep -c 'exit 124' "$LOG")"

# Order matters. A timed-out run may have printed a summary before it was killed,
# and a total outage must not be read as a quiet night.
if [ "$TIMED_OUT" != "0" ]; then
  echo timeout
elif [ -z "${UPSERTED:-}" ]; then
  # No summary at all: the run did not reach the end.
  echo error
elif [ "$UPSERTED" -eq 0 ] && [ -n "${BAD_SOURCES:-}" ] && [ "$BAD_SOURCES" -gt 0 ]; then
  # Nothing arrived AND sources died. Calling this "empty" would make a total
  # outage indistinguishable from a night when Berlin simply had no events.
  echo error
elif [ "$UPSERTED" -eq 0 ]; then
  echo empty
elif [ -n "${BAD_SOURCES:-}" ] && [ "$BAD_SOURCES" -gt 0 ]; then
  # Events arrived, so the run is not broken — but a source is down, and saying
  # "ok" here is how a dead scraper goes unnoticed for months.
  echo degraded
else
  echo ok
fi
