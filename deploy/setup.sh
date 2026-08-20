#!/usr/bin/env bash
# One-time setup for a Hetzner (or any Ubuntu 24.04) box that runs the Pulse
# pipeline. Idempotent: safe to re-run after a change or a failed attempt.
#
# Why this exists as a script rather than a list of commands in a wiki: a server
# configured by hand is a server nobody can rebuild. Everything here is in git.
#
#   ssh <user>@<host>
#   git clone https://github.com/SolarFab/nachtkarte-pipeline.git ~/pulse
#   bash ~/pulse/deploy/setup.sh
#
# Afterwards: create ~/pulse/.env (see .env.example) and install the cron entry
# printed at the end.
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/pulse}"
LOG_DIR="${LOG_DIR:-$HOME/pulse-logs}"

say() { printf '\n\033[1m▶ %s\033[0m\n' "$*"; }

say "System packages"
sudo apt-get update -qq
# No python here on purpose: uv downloads and manages its own interpreter, so the
# box's Python version stops mattering and an OS upgrade cannot change ours.
sudo apt-get install -y -qq curl git ca-certificates

say "uv (pinned installer, not a moving 'latest')"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
grep -qs '.local/bin' "$HOME/.profile" || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.profile"
uv --version

say "Swap (4G)"
# The box this was written for had 3.7G RAM and ZERO swap. With no swap a memory
# spike does not slow down, it kills — and the OOM killer picks the biggest
# process, which may well be n8n rather than the scrape that caused it. Swap
# turns a hard kill into a slow minute.
if ! swapon --show | grep -q .; then
  sudo fallocate -l 4G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap -q /swapfile
  sudo swapon /swapfile
  grep -qs '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  echo "swap enabled"
else
  echo "swap already present, leaving it alone"
fi

say "Python dependencies"
cd "$REPO_DIR"
uv python install          # honours requires-python from pyproject.toml
uv sync --frozen

say "Playwright browser"
# Only one scraper (themakery) needs a browser, but it needs a real one.
# `--with-deps` maps Chromium's shared libraries onto apt packages, and that map
# only covers Ubuntu releases Playwright already knows. On a very new release it
# can fail; 24.04 LTS is the safe choice. Failing here is not fatal — every other
# scraper is plain HTTP — so say so clearly and carry on rather than aborting a
# setup that is otherwise complete.
if ! uv run playwright install --with-deps chromium; then
  echo "!! Playwright setup failed — themakery (the only browser scraper) will not run."
  echo "!! Everything else is unaffected. On a non-LTS Ubuntu, try 24.04 instead."
fi

say "Log directory"
mkdir -p "$LOG_DIR"

say "Done"
cat <<EOF

Two things left, both yours:

1. Secrets. Create $REPO_DIR/.env from .env.example and lock it down:

     nano $REPO_DIR/.env
     chmod 600 $REPO_DIR/.env

2. Schedule. Add this to \`crontab -e\` — 02:00 UTC, same slot the GitHub
   workflow used, so the two never overlap while you run them in parallel:

     0 2 * * * $REPO_DIR/deploy/run-scrape.sh >> $LOG_DIR/cron.log 2>&1

   Set PULSE_ALERT_WEBHOOK in .env first, or a failing run will be silent —
   which is the failure mode that let the old nightly job do nothing for weeks.

Test it once by hand before trusting the cron:

     $REPO_DIR/deploy/run-scrape.sh
EOF
