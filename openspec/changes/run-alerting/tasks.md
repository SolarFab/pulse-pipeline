# Tasks — Run alerting (issue #12)
- [ ] 1.1 n8n workflow: webhook in, route by `status`, deliver to the chosen channel
- [ ] 1.2 Set `PULSE_ALERT_WEBHOOK` in the server `.env` (chmod 600)
- [ ] 1.3 Verify each verdict end to end by feeding a synthetic log to run-scrape.sh
- [ ] 2.1 Dead-man's switch: n8n expects a ping by 06:00 UTC and complains if none arrived
- [ ] 2.2 Verify by stopping the cron for one night on purpose
- [ ] 3.1 Confirm SC-AL-05 by pointing the webhook at an unreachable host mid-run
