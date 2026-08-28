# Running the pipeline on a server

The nightly scrape used to run in GitHub Actions. Two things ended that:

- **A 120-minute cap.** Seven of eight runs were cancelled mid-scrape. The
  catalogue only grew on the days a run happened to finish.
- **Actions minutes.** The repo is private, so minutes are metered. At ~130
  minutes a day the 2,000-minute allowance ran out on 17 August and *every*
  scheduled run failed in four seconds — silently, as far as the data was
  concerned. No new events arrived for four days before anyone noticed.

A €6.53/month box has neither limit. Nothing else moves: Supabase still hosts the
database, Vercel still serves the web app. Only the Python pipeline relocates, and
because it is a batch job, an outage means a stale catalogue for a day — the same
failure the timeouts already caused.

## Setup

```bash
ssh <user>@<host>
git clone https://github.com/SolarFab/nachtkarte-pipeline.git ~/pulse
bash ~/pulse/deploy/setup.sh
```

`setup.sh` installs uv (which brings its own Python, so the OS version stops
mattering), the project dependencies, Chromium for the one scraper that needs a
browser, and **4 GB of swap**. The swap is not incidental: a 4 GB box with none at
all turns a memory spike into an instant kill, and the OOM killer picks the
largest process, not the guilty one.

It is idempotent — re-run it after a change or a failed attempt.

Then create `~/pulse/.env` from `.env.example` and lock it down:

```bash
nano ~/pulse/.env && chmod 600 ~/pulse/.env
```

Finally, schedule it (`crontab -e`):

```
0 2 * * * /home/<user>/pulse/deploy/run-scrape.sh >> /home/<user>/pulse-logs/cron.log 2>&1
```

02:00 UTC is the slot the GitHub workflow used, so the two never overlap while
both exist.

## What run-scrape.sh does beyond running the scrape

`flock` — one run at a time. A scrape that overruns into the next night must not
have a second copy competing for the same rows and the same 4 GB.

`git pull` — the deploy step. Push to main, and the next run picks it up.

`timeout 240m` — a runaway guard, not a schedule. The run takes ~100 minutes;
this only catches a hang.

**A verdict based on output, not exit code.** The script looks for the pipeline's
own `Total: N upserted` line and classifies the run as `ok`, `empty`, `error` or
`timeout`. This matters more than it sounds: the old harvest job exited 0 while
doing nothing for weeks, and everything downstream reported success. An exit code
is not evidence that work happened.

Logs land in `~/pulse-logs/scrape-<timestamp>.log`, kept for 14 days.

## Alerting — deliberately not built yet

Set `PULSE_ALERT_WEBHOOK` in `.env` and every run POSTs a small JSON verdict to
it; leave it unset and the verdict only goes to the log. The payload is generic
(`status`, `host`, `started`, `summary`) so an n8n webhook can route it to mail,
Telegram or anything else without this script knowing which.

Until something consumes it, **a failed run is silent**. That is the one
capability GitHub Actions gave for free and a bare cron does not, and it is worth
closing before this is the only path the catalogue depends on.

## Checking on it

```bash
tail -f ~/pulse-logs/cron.log                 # verdicts, one line per run
ls -lt ~/pulse-logs/ | head                   # recent runs
grep -E '▶|✓|✗' ~/pulse-logs/scrape-*.log     # per-scraper results
~/pulse/deploy/run-scrape.sh                  # run by hand
```

## Rollback

The GitHub workflow is not deleted, only unscheduled. Restore the `schedule:`
block in `.github/workflows/scrape.yml` and it takes over again — assuming the
Actions allowance has reset.

**Stop the Hetzner cron first.** Both run at 02:00 UTC, so restoring the
schedule without commenting out the crontab line gives you two scrapes
competing for the same rows. This is a rollback, not a second copy.
