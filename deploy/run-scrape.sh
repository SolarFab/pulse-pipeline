#!/usr/bin/env bash
# The nightly pipeline run. Invoked by cron; safe to run by hand.
#
# Replaces the GitHub Actions workflow, which had two problems this fixes:
#   - a 120-minute cap that cancelled 7 of 8 runs mid-scrape
#   - Actions minutes on a private repo, which ran out and stopped everything
#
# It also has to replace what Actions gave for free and a bare cron does not:
# a visible history and a shout when something breaks. Both are handled below,
# because the failure mode we already lived through is a job that reports success
# while doing nothing.
set -uo pipefail

REPO_DIR="${REPO_DIR:-$HOME/pulse}"
LOG_DIR="${LOG_DIR:-$HOME/pulse-logs}"
LOCK_FILE="/tmp/pulse-scrape.lock"
KEEP_LOGS=14
# Measured on the first real run: 3h34m wall clock, 206 minutes of it scraping.
# That is well past the 120-minute cap that was cancelling this job on GitHub —
# the migration was a precondition, not a tuning exercise. 300 gives ~45 minutes
# of headroom for a slow night; it is a runaway guard, not a schedule.
MAX_MINUTES="${MAX_MINUTES:-300}"

mkdir -p "$LOG_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/scrape-$STAMP.log"

# One run at a time. A scrape that overruns into the next night must not have a
# second copy competing for the same rows and the same 4 GB of RAM.
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "another run is still going; skipping $STAMP" >> "$LOG_DIR/cron.log"
  exit 0
fi

cd "$REPO_DIR" || exit 1
set -a; [ -f .env ] && . ./.env; set +a
export PATH="$HOME/.local/bin:$PATH"

notify() {  # status, summary
  local status="$1" summary="$2"
  echo "[$status] $summary"
  [ -n "${PULSE_ALERT_WEBHOOK:-}" ] || return 0

  # The whole payload is assembled in Python, on stdin, rather than with printf.
  # Berlin event titles are full of umlauts, and cron runs with a C locale where
  # shell printf mangles them — a malformed body would turn every alert into a
  # silent failure, which is the one thing this function exists to prevent.
  # Deliberately generic JSON: an n8n webhook can route it to Telegram, mail or
  # anything else without this script knowing which.
  local body
  body="$(STATUS="$status" HOST="$(hostname)" STARTED="$STAMP" \
    python3 -c 'import json,os,sys; print(json.dumps({
        "source": "pulse-scrape",
        "status": os.environ["STATUS"],
        "host":   os.environ["HOST"],
        "started": os.environ["STARTED"],
        "summary": sys.stdin.read()[:4000],
    }))' <<<"$summary")" || { echo "warning: could not build alert payload"; return 0; }

  curl -fsS -m 20 -X POST "$PULSE_ALERT_WEBHOOK" \
    -H 'Content-Type: application/json; charset=utf-8' \
    --data-binary "$body" >/dev/null \
    || echo "warning: could not reach PULSE_ALERT_WEBHOOK"
}

{
  echo "=== pulse scrape $STAMP on $(hostname)"
  git pull --ff-only 2>&1
  uv sync --frozen 2>&1
  echo "=== run"
  timeout --signal=TERM --kill-after=60 "${MAX_MINUTES}m" uv run python main.py --run-all 2>&1
  echo "=== exit $?"
} >> "$LOG" 2>&1

# The pipeline's own summary line is the honest signal, not the exit code — a run
# that scrapes nothing still exits 0. Since #6 the line also carries how many
# SOURCES failed, which is a different number from how many rows failed to
# upsert; before that, a night where half the sources died still read "0 failed".
#
#   Total: 18444 upserted, 1 failed, 2 source(s) failed (venue_website, instagram)
#
RESULT="$(grep -E 'Total: [0-9]+ upserted' "$LOG" | tail -1)"
UPSERTED="$(printf '%s' "$RESULT" | sed -nE 's/.*Total: ([0-9]+) upserted.*/\1/p')"
BAD_SOURCES="$(printf '%s' "$RESULT" | sed -nE 's/.*, ([0-9]+) source\(s\) failed.*/\1/p')"
TIMED_OUT="$(grep -c 'exit 124' "$LOG")"

if [ "$TIMED_OUT" != "0" ]; then
  notify "timeout" "killed after ${MAX_MINUTES}m. $(tail -5 "$LOG")"
elif [ -z "${UPSERTED:-}" ]; then
  notify "error" "no 'Total: N upserted' line — the run did not finish. $(tail -15 "$LOG")"
elif [ "$UPSERTED" -eq 0 ] && [ -n "${BAD_SOURCES:-}" ] && [ "$BAD_SOURCES" -gt 0 ]; then
  # Nothing arrived AND sources died: a total outage, not a quiet night. An
  # earlier version called this "empty", which made "every scraper ran fine and
  # Berlin had no events" indistinguishable from "every scraper crashed".
  notify "error" "no events and $BAD_SOURCES source(s) failed. $RESULT"
elif [ "$UPSERTED" -eq 0 ]; then
  notify "empty" "every source ran, none produced events. $RESULT"
elif [ -n "${BAD_SOURCES:-}" ] && [ "$BAD_SOURCES" -gt 0 ]; then
  # Events still arrived, so this is not a broken run — but a source is down and
  # saying "ok" here is how a dead scraper goes unnoticed for months.
  notify "degraded" "$RESULT — log $(basename "$LOG")"
else
  notify "ok" "$RESULT (log $(basename "$LOG"))"
fi

# Keep a fortnight; a 4 GB box with 19 GB free should not fill up with logs.
find "$LOG_DIR" -name 'scrape-*.log' -type f -mtime "+$KEEP_LOGS" -delete
