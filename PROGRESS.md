# NachtKarte Pipeline — Progress Tracker

_Last updated: 2026-03-12 11:05_

---

## FIRST THING TO DO IN NEXT SESSION

### 0. Activate the Python venv
```bash
cd /Users/solarlord/Projects/event-map
source .venv/bin/activate
```

### 1. Test resident_advisor (needs Playwright)
```bash
playwright install chromium   # if not already done
DRY_RUN=true python main.py --run resident_advisor
```

### 2. Run full pipeline
```bash
python main.py --run-all
```
Goal: 500+ events in the DB from multiple sources. Currently at ~1073 events.

### 3. Consider next steps
- Fix `holzmarkt.py` if/when holzmarkt.com comes back online (currently timing out)
- Get EVENTBRITE_API_KEY and MEETUP_API_KEY for more data sources
- Fix duplicate fingerprint issue in bulk upsert (currently falls back to individual inserts)

---

## What Was Completed (2026-03-12 Session 3)

- ✅ **tip_berlin.py rewritten** — Switched from WP REST API to dedicated event calendar at `tip-berlin.de/event/`. Scrapes 10 category listing pages, collects unique event URLs, fetches JSON-LD Event schema from each. **307 events upserted** (up from 1).
- ✅ **resident_advisor.py rewritten** — Dropped Playwright (RA blocks headless browsers), now hits RA's public GraphQL API directly. 14-day window, paginated. **228 events upserted**. Added `post()` method to BaseScraper.

## What Was Completed (2026-03-12 Session 2)

- ✅ **berlin_de → DB** — 44 events upserted
- ✅ **markthalle_neun → DB** — 11 events upserted
- ✅ **mauerpark → DB** — 17 events upserted
- ✅ **nowkoelln → DB** — 5 events upserted
- ✅ **rausgegangen → DB** — 147 events upserted (biggest source after kulturdaten!)
- ✅ **klunkerkranich.py fixed** — Rewrote HTML parser for wp_events plugin (was looking for Tribe Events). Extracts dates from URL + time from card text. 13 events upserted.
- ❌ **holzmarkt.py** — holzmarkt.com is completely down (ConnectTimeout). Cannot fix until site recovers.

## What Was Completed (2026-03-12 Session 1)

- ✅ **markthalle_neun.py** — Rewrote scraper. Now fetches `/events` listing, follows each `/events/[slug]` link, parses German dates from individual pages. JSON-LD first, HTML fallback. Dry-run: 11 events.
- ✅ **berlin_de.py** — Rewrote scraper. Switched from broken category URLs (410 Gone) to month-based URLs (`/events/jahresuebersicht/maerz/`). Multi-strategy date extraction. Category=None → Claude categorizer. Dry-run: 44 events.
- ✅ **DB schema applied** — PostGIS enabled, venues + events tables, indexes, RLS policies, updated_at trigger. All via Supabase SQL editor.
- ✅ **First real DB write** — `KULTURDATEN_MAX_PAGES=3 python main.py --run kulturdaten` → 300 events upserted, 0 failed.

---

## Architecture

```
event-map/
├── main.py                    # CLI: --run, --run-all, --dry-run, --list, --schedule
├── pipeline/
│   ├── normalizer.py          # Pydantic RawEvent, fingerprinting, date parsing
│   ├── categorizer.py         # Claude Haiku categorization
│   └── scheduler.py           # APScheduler cron jobs
├── scrapers/
│   ├── base.py                # BaseScraper: scrape() → normalize → categorize → upsert
│   ├── kulturdaten.py         # ✅ IN DB (300 events)
│   ├── rausgegangen.py        # ✅ IN DB (147 events)
│   ├── tip_berlin.py          # ✅ IN DB (307 events — event calendar)
│   ├── berlin_de.py           # ✅ IN DB (44 events)
│   ├── eventbrite.py          # 🔶 Needs EVENTBRITE_API_KEY
│   ├── meetup.py              # 🔶 Needs MEETUP_API_KEY
│   ├── resident_advisor.py    # ✅ IN DB (228 events — GraphQL API)
│   └── venues/
│       ├── markthalle_neun.py # ✅ IN DB (11 events)
│       ├── nowkoelln.py       # ✅ IN DB (5 events)
│       ├── mauerpark.py       # ✅ IN DB (17 events)
│       ├── klunkerkranich.py  # ✅ IN DB (13 events)
│       └── holzmarkt.py       # ❌ Site down (ConnectTimeout)
└── db/
    ├── schema.sql             # ✅ APPLIED
    └── supabase.py            # upsert_events(), on_conflict="fingerprint"
```

---

## Scraper Status

| Scraper | Status | Events | Notes |
|---------|--------|--------|-------|
| kulturdaten | ✅ In DB | 300 | 3 pages. Full run = 13,800+ |
| rausgegangen | ✅ In DB | 147 | Biggest web scraper source |
| berlin_de | ✅ In DB | 44 | Month-based URLs |
| mauerpark | ✅ In DB | 17 | Every Sunday Apr–Oct |
| klunkerkranich | ✅ In DB | 13 | Fixed: wp_events HTML parser |
| markthalle_neun | ✅ In DB | 11 | Follows event links, German dates |
| nowkoelln | ✅ In DB | 5 | Biweekly Sundays |
| tip_berlin | ✅ In DB | 307 | Rewritten: event calendar with JSON-LD |
| holzmarkt | ❌ Site down | 0 | holzmarkt.com ConnectTimeout |
| eventbrite | 🔶 No key | — | Needs EVENTBRITE_API_KEY |
| meetup | 🔶 No key | — | Needs MEETUP_API_KEY |
| resident_advisor | ✅ In DB | 228 | Rewritten: GraphQL API, no Playwright |

---

## Known Bugs Already Fixed

- Claude returns markdown-fenced JSON → strip ` ```json ` in `pipeline/categorizer.py`
- `T24:00:00` datetime → replace + add 1 day in `pipeline/normalizer.py`
- Rausgegangen 404 → use `/berlin/kategorie/...` category pages
- kulturdaten wrong BASE_URL → `https://api-v2.kulturdaten.berlin/api`
- kulturdaten data structure → `attractions[0].referenceLabel.de` for title
- markthalle_neun: old URL `/veranstaltungen/` → new URL `/events`, follow individual pages for dates
- berlin_de: category URLs return 410 → switched to month-based `/events/jahresuebersicht/{month}/`
- klunkerkranich: was looking for Tribe Events classes, site uses `wp_events` plugin with `type-wp_events` articles
- tip_berlin: was pulling ALL posts (years of articles) → rewrote to scrape dedicated event calendar at `/event/` with JSON-LD
- Bulk upsert duplicate fingerprint → falls back to individual row upserts (works but slower)

---

## Credentials

All credentials live in `.env` (pipeline) and `web/.env.local` (web app) — never in this file or git.
NOTE (2026-07-09): the ANTHROPIC_API_KEY in both files returns 401 (revoked) — generate a new key at console.anthropic.com and update both files, or chat + categorizer stay broken.

Python 3.11: `/opt/homebrew/bin/python3.11`

---

## Key Commands

```bash
# Activate venv
source .venv/bin/activate

# Dry run single scraper
DRY_RUN=true python main.py --run kulturdaten

# Limit pages for testing
KULTURDATEN_MAX_PAGES=3 python main.py --run kulturdaten

# Run single scraper for real
python main.py --run berlin_de

# Run all scrapers
python main.py --run-all

# Start scheduler
python main.py --schedule
```
