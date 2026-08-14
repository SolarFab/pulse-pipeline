# Backlog

Things found and deliberately deferred. Not a task tracker — each entry records what
was measured, so picking it up later does not mean re-investigating it.

Substantial items graduate to an OpenSpec change in `openspec/changes/<name>/`.

---

## Flyer scanner: move to OpenRouter, then validate, then close the HITL loop

**Status:** deferred 2026-08-14. Feature is currently dead in production.

### What exists

- `web/src/components/ScanFlyer.tsx` — the UI
- `POST /api/events/scan` — image → Claude Vision → extracted event JSON
- `PUT  /api/events/scan` — writes the confirmed event with `status: "pending"`

### What is broken or missing

1. **The extraction call is dead.** It uses the Anthropic SDK directly with
   `ANTHROPIC_API_KEY`, which returns 401 (same provenance as the expired
   OpenRouter key). Every scan fails.
2. **No event has ever been saved.** All 82,823 rows in `events` are `status =
   'active'`; there has never been a single `pending` row. The write path is
   unproven, not just the read path.
3. **No moderation exists.** The string `pending` appears in exactly one file —
   the route that writes it. Nothing reads it, so an approved-by-nobody event
   would sit there forever. There is no queue, no UI, no notification.
4. **The prompt has a frozen date:** `"calculate the next occurrence from today
   (2026-03-22)"`. A flyer that says only "Samstag" resolves into March.

### Target flow (agreed with the user)

    user photographs a flyer
      -> extract event data
      -> submit
      -> HITL notification to the operator (email / Slack / Telegram)
      -> operator verifies
      -> event goes live
      -> notify the submitting user, if we can reach them

### Order of work

1. **Move extraction to OpenRouter**, reading `OPENROUTER_FLYER_SCAN_KEY` —
   its OWN key, already created and set in Vercel. Not a share of the
   concierge's: a vision call costs multiples of a chat turn (the image alone is
   thousands of tokens), and the endpoint takes 8 MB uploads, so the abuse
   profile differs too. The point is blast radius as much as accounting — a
   scanner being spammed must not drain the budget the chat depends on.
   Model behind a `SCAN_MODEL` env var, as with `CHAT_MODEL`. Note the
   request-body shape changes: OpenAI-compatible `image_url` with a data URI,
   not Anthropic's `source.base64` block.

   Do NOT silently fall back to `OPENROUTER_API_KEY` when the scan key is
   missing: a forgotten variable would then quietly bill the concierge and
   defeat the separation. Fail loudly instead.
2. **Fix the frozen date** — derive it from the request, in Europe/Berlin.
3. **Validate before building further.** 243 vision models are available through
   the gateway at wildly different prices (from $0.03/M to several dollars). Run
   real Berlin flyers — German text, stylised fonts, handwritten dates — through
   a handful of candidates and compare extraction quality, cost and latency, the
   same way the chat model was chosen in `scripts/benchmark_stage2.py`. Pick on
   evidence, not on price.
4. **Only then build the HITL loop.** It is worthless if step 3 shows extraction
   is not good enough to review.

### Open questions for the HITL design

- Which channel for the operator? Telegram is the cheapest to build (bot token,
  one HTTP call, buttons for approve/reject). Email needs a sender domain.
- Approve/reject needs an authenticated action. A signed one-time link per event
  avoids building an admin UI for a single operator.
- "Notify the submitting user": `NotificationSettings.tsx` already exists and
  VAPID keys are configured, so web push may already be the cheapest route —
  check whether subscriptions are actually being stored before assuming email.
- Scanned events bypass the pipeline's categorizer and geocoder today. Decide
  whether approval should push them through the same normalize → categorize →
  facets → embed path every other source takes, so they are not second-class
  rows in search.
