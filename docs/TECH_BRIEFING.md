# Pulse — Technical Briefing

**Berlin Event Discovery Platform**
Last updated: 2026-03-24

---

## Overview

Pulse is a real-time Berlin event discovery platform. It scrapes 21 data sources daily, categorizes events with Claude AI, and serves them on an interactive map with an AI chat concierge. Users can also snap a photo of a street flyer to add events.

**Live:** https://event-map-ten.vercel.app
**Users:** 10 registered (beta)
**Events in DB:** ~36,000 total, ~3,000 per week

---

## Tech Stack Summary

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, TypeScript 5, Tailwind CSS 4 |
| Map | MapLibre GL (open-source Mapbox alternative) + CartoDB Positron tiles |
| Backend API | Next.js API routes (serverless on Vercel) |
| Database | Supabase (managed PostgreSQL + PostGIS) |
| Auth | Supabase Auth (email/password + Google OAuth) |
| AI/LLM | Anthropic Claude (Haiku for categorization & chat, Sonnet for vision) |
| Pipeline | Python 3.11 (scrapers + data processing) |
| Hosting | Vercel (frontend), GitHub Actions (pipeline) |
| Geocoding | Nominatim (OpenStreetMap) + venue DB cache |

---

## Database Architecture

**PostgreSQL on Supabase** — relational, not vector. No embeddings or vector search. The LLM accesses the database indirectly:

1. **Chat API** (`/api/chat`) queries Supabase via the REST API with filters (time window, category, text search), then passes matching events as plain text context in the Claude system prompt.
2. **Categorizer** (pipeline) sends raw event data to Claude, gets back structured JSON (category, subcategory, tags), then writes it to the DB.

### Core Tables

**`events`** — 36K+ rows
- title, venue_name, venue_id (FK), start_time, end_time
- category, subcategory, tags (text array)
- description, price, price_cents, image_url
- source, source_url, fingerprint (SHA256 dedup)
- status (active/pending/rejected), quality_score (0.0-1.0)

**`venues`** — ~800 rows
- name, lat, lng, neighborhood, address
- website_url, instagram_handle, google_place_id

**`events_with_coords`** — Postgres VIEW
- Resolves lat/lng from venues table via LEFT JOIN
- `COALESCE(v.lat, e.lat)` — prefers venue coords, falls back to event-level
- All frontend queries hit this view, not the events table directly

**Other tables:** profiles, feedback, interested_venues, venue_tips

### Indexes
- PostGIS geospatial (GiST) on lat/lng
- Composite on start_time + end_time
- Category + is_active
- Fingerprint (unique, for dedup)

### Row-Level Security
- Public: read active events only
- Public: insert community submissions (status=pending)
- Service role: full access (pipeline bypasses RLS)

---

## Scrapers — 21 Data Sources

### Tier 1: Public APIs (daily 06:00)
| Scraper | Source | Events |
|---------|--------|--------|
| `kulturdaten.py` | kulturdaten.berlin API | ~14,000 |
| `eventbrite.py` | Eventbrite Destination Search | ~500 |
| `meetup.py` | Meetup.com GraphQL | needs key |

### Tier 2: HTML Scrapers (daily 06:30)
| Scraper | Source | Method |
|---------|--------|--------|
| `tip_berlin.py` | tip-berlin.de | JSON-LD extraction |
| `berlin_de.py` | berlin.de/en | HTML parsing |
| `rausgegangen.py` | rausgegangen.de | JSON-LD + HTML (2x daily) |
| `resident_advisor.py` | ra.co | GraphQL API (03:00) |
| `luma.py` | lu.ma | Discover API |
| `bandsintown.py` | Bandsintown | Artist API |
| `berlinmitkind.py` | berlinmitkind.de | WordPress REST + RSS |

### Tier 3: Venue-Specific (daily 07:00)
markthalle_neun, klunkerkranich, holzmarkt, nowkoelln, mauerpark, wochenmaerkte, jazzclubs, planetarium, startbahn, feine_klingen, froschkoenig

### Pipeline Flow
```
scrape() → normalize → dedup (fingerprint) → geocode → categorize → upsert
```

- **Normalize:** Pydantic validation, date parsing, price extraction
- **Dedup:** SHA256 of `lower(title) + date` — skips existing events
- **Geocode:** venues DB → hardcoded dict (160+ venues) → Nominatim API
- **Categorize:** Claude Haiku, batches of 10, skips already-categorized
- **Upsert:** Supabase, chunks of 500, conflict on fingerprint

---

## Taxonomy & Categorization System

Our categorization is a **3-layer system** that combines rule-based keyword matching with LLM intelligence. The goal: every event gets a category, subcategory, and up to 5 English tags — even if the source data is in German with no metadata.

### Layer 1: Source Tags (rule-based, instant)

Some scrapers (especially kulturdaten.berlin) provide their own taxonomy tags. We map these directly to our categories:

```
attraction.category.Concerts  →  music / live-concert
attraction.category.Clubs     →  nightlife / club-night
attraction.category.Markets   →  markets
attraction.category.Theater   →  culture / theater
```

~60 source tag mappings cover the kulturdaten dataset (our largest source at ~14K events).

### Layer 2: Keyword Matching (rule-based, instant)

For events without source tags, we match German + English keywords in the title/description against our taxonomy. This is a dictionary of **3,000+ keyword-to-subcategory mappings**:

```
"Jazzkonzert"        →  music / jazz-blues
"Flohmarkt"          →  markets / flea-market
"Kindertheater"      →  family / kids-program
"Vernissage"         →  culture / gallery
"Yoga im Park"       →  outdoors / yoga-fitness
"Pub Quiz"           →  nightlife / bar-event
```

Keywords are matched case-insensitively with word boundaries. This layer catches ~70% of events before needing the LLM.

### Layer 3: Claude LLM Categorization (AI, for remaining events)

Events that couldn't be categorized by layers 1 or 2 go to **Claude Haiku 4.5** in batches of 10. The LLM receives:
- title, venue_name, description (capped at 800 chars), price, source

And returns:
- **category** (one of 9)
- **subcategory** (from predefined list per category)
- **tags** — up to 5 English tags with the German keywords that triggered them
- **quality_score** (0.0-1.0) — filters out non-events like "police station opening hours"

### Self-Learning Keyword Expansion

The LLM returns bilingual tags: `{"en": "pottery", "de": ["Töpfern", "Keramik"]}`. New German keywords the LLM discovers are saved to `data/new_keywords.json` and can be merged back into the taxonomy dictionary. This means the system learns new German keywords over time, reducing future LLM calls.

### The 9 Categories

| Category | Subcategories | Example |
|----------|--------------|---------|
| **music** | jazz-blues, electronic, classical, rock-pop, hip-hop, live-concert, world-folk, latin | Jazz night at A-Trane |
| **nightlife** | club-night, bar-event, party, comedy, karaoke | Techno at Berghain |
| **culture** | exhibition, theater, cinema, reading, gallery, festival | Sculpture at KW Institute |
| **food** | brunch, tasting, pop-up, dining-event, food-market, weekly-market | Street Food Thursday |
| **markets** | flea-market, design-market, pop-up-fashion, secondhand, craft-market | Mauerpark Flohmarkt |
| **workshops** | creative-workshop, language, digital-skills, dance-class, craft | Pottery workshop in Neukölln |
| **meetups** | networking, community, tech-startup, talk-panel, activism | Berlin.js meetup |
| **outdoors** | walking-tour, sports, yoga-fitness, bike-tour, outdoor-cinema | Yoga in Volkspark |
| **family** | kids-program, family-event, playground, museum-for-kids | Puppet theater at FEZ |

### Key Categorization Rules

1. Categorize by **primary activity** the attendee goes for, not venue type
2. Live music at a bar → `music`, not `nightlife`
3. DJ set / techno → `nightlife`, even with live music elements
4. Children's theater → `family`, not `culture`
5. Flohmarkt/Trödelmarkt → `markets` (shopping), Wochenmarkt → `food` (eating)
6. Events with quality_score 0.0 are filtered out (administrative, not real events)

### Cost Optimization

- Layer 1 + 2 handle ~70-80% of events (zero LLM cost)
- Prompt caching on the system prompt (5-min TTL, saves ~50% on repeated calls)
- Batch processing: 10 events per API call instead of 1
- Skip already-categorized events in DB (checked before LLM call)
- Result: a daily scrape of ~3,000 events typically needs <500 LLM calls

---

## AI / LLM Usage

### 1. Event Categorization (Pipeline)
- **Model:** Claude Haiku 4.5 (cheapest)
- **When:** During daily scrape, for new/uncategorized events only
- **Batch:** 10 events per API call with prompt caching
- **Output:** category, subcategory, up to 5 tags, quality_score
- **Cost optimization:** Skips events already categorized in DB

### 2. Chat Recommendations (Frontend API)
- **Model:** Claude Haiku 4.5
- **How it works:**
  1. User asks "best techno tonight?"
  2. API parses intent → time window + category keywords
  3. Queries Supabase for matching events (up to 100)
  4. Sends events as text context in system prompt
  5. Claude returns 3-5 opinionated recommendations with event IDs
- **No vector DB / no embeddings** — pure keyword filtering + SQL, then LLM ranking
- **Bilingual:** Responds in the language the user writes in

### 3. Flyer Scanner (Frontend API)
- **Model:** Claude Sonnet 4 (vision-capable)
- **Flow:** User snaps flyer → base64 image sent to Claude → extracts structured event data → user reviews/edits → saved to DB
- **Source:** `community-scan`

---

## Frontend Architecture

### Pages
- `/` — Main map view (MapLibre GL + event pins + filters)
- `/login` — Email/password + Google OAuth
- `/signup` — Registration with email confirmation
- `/forgot-password` — Password reset

### Key Components
| Component | Purpose |
|-----------|---------|
| `EventMap.tsx` | MapLibre GL map with emoji category pins, clustering |
| `Filters.tsx` | Time filter (now/tonight/tomorrow/weekend) + 9 category pills + subcategories |
| `ChatPanel.tsx` | AI chat panel, streaming responses, event highlighting on map |
| `EventDetail.tsx` | Swipe-up event detail sheet with bookmarks, calendar export, share |
| `CreateEvent.tsx` | 3 options: host registration, venue tip, flyer scan |
| `ScanFlyer.tsx` | Camera capture → Claude Vision → review form → save |
| `FeedbackButton.tsx` | Floating beta feedback button (name, message, thumbs up/down) |

### API Routes (serverless on Vercel)
| Route | Method | Purpose |
|-------|--------|---------|
| `/api/events` | GET | Fetch events by time/category/tag/IDs |
| `/api/events/search` | GET | Text search across title/venue/description |
| `/api/events/scan` | POST | Send flyer image → Claude Vision extraction |
| `/api/events/scan` | PUT | Save confirmed scanned event to DB |
| `/api/chat` | POST | AI chat with streaming SSE response |

---

## Deployment & CI/CD

### Frontend (Vercel)
- Auto-deploys on push to `main` branch
- Serverless API routes for chat, events, scan
- Environment: SUPABASE_URL, SUPABASE_SERVICE_KEY, ANTHROPIC_API_KEY, NEXT_PUBLIC_SUPABASE_*

### Pipeline (GitHub Actions)
- **Schedule:** Daily at 02:00 UTC (04:00 Berlin)
- **Workflow:** `.github/workflows/scrape.yml`
- **Runtime:** Python 3.11, 45-minute timeout
- **Command:** `python main.py --run-all`
- **Secrets:** SUPABASE_URL, SUPABASE_SERVICE_KEY, ANTHROPIC_API_KEY, EVENTBRITE_API_KEY

### Repositories
- **Backend/Pipeline:** github.com/SolarFab/nachtkarte-pipeline
- **Frontend:** github.com/SolarFab/nachtkarte

---

## Key Metrics (as of 2026-03-24)

- **Total events in DB:** ~36,000
- **Events with coordinates:** 98.9%
- **Events per week:** ~2,500-3,000
- **Venues in DB:** ~800
- **Registered users:** 10 (beta)
- **Scrapers:** 21 (13 content + 8 venue-specific)
- **Daily scrape time:** ~10-15 minutes
- **LLM cost:** Minimal (Haiku for categorization, skips known events)

---

## What We Don't Use

- **No vector database** — no Pinecone, Weaviate, pgvector
- **No embeddings** — events are matched via SQL filters (time, category, text ILIKE)
- **No RAG** — the chat sends filtered events as plain text context, not retrieved vectors
- **No Redis/cache layer** — Supabase handles all queries directly
- **No message queue** — scrapers run sequentially via APScheduler
