# A failed nightly run must reach a human

## Why
The nightly scrape moved from GitHub Actions to the Hetzner box. Actions emailed on failure; a
cron on a server says nothing. `deploy/run-scrape.sh` already computes a verdict and will POST it
to `PULSE_ALERT_WEBHOOK`, but that variable is unset, so the verdict reaches a log file nobody
opens.

This project has now produced "green but dead" three times in three systems: the discovery harvest
job succeeding in 8 seconds while doing nothing for weeks; GitHub Actions reporting success on runs
it had cancelled at the 120-minute cap; Tailscale reporting `Online: true` for a node that answered
nothing. The nightly scrape is now the only path keeping the catalogue current, and it is the one
with no alarm attached.

Who benefits: the operator, who currently learns about a broken catalogue from a user.

## What Changes
- `PULSE_ALERT_WEBHOOK` points at an n8n webhook that routes to a real channel
- A run that ends in anything other than `ok` produces a message
- A run that never starts also produces a message

## Capabilities
### Modified Capabilities
- `pipeline-observability` — the verdict reaches a person, not only a log.

## Impact
Server `.env` and an n8n workflow. `run-scrape.sh` is unchanged: it already posts a generic
payload and deliberately knows nothing about the destination.

## Non-goals
Escalation policy, on-call rotation, dashboards, and alerting on data gauges — the gauges ticket
depends on this one but owns its own thresholds.

## Risk
Additive and outside the data path. Failure of the alerting must never break the scrape.
