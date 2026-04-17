# NachtKarte

AI-powered real-time event discovery map for Berlin. Aggregates events from 21+ data sources, plots them on a dark-themed interactive map, and lets you find what's happening right now through smart filters or natural language chat.

**Live:** [nachtkarte.app](https://event-map-ten.vercel.app)

![Next.js](https://img.shields.io/badge/Next.js-16-black)
![React](https://img.shields.io/badge/React-19-61DAFB)
![Python](https://img.shields.io/badge/Python-3.11-3776AB)
![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E)
![Claude AI](https://img.shields.io/badge/Claude-AI--powered-D97706)

## Features

- **Interactive Event Map** -- Dark-themed MapLibre GL map with emoji-colored pins by category, clustering, and smooth animations
- **AI Chat Concierge** -- Ask in natural language ("best jazz tonight?") and get personalized recommendations with events highlighted on the map
- **Flyer Scanner** -- Snap a photo of a street flyer and Claude Vision extracts the event details automatically
- **Smart Filters** -- Time filters (Right Now, Tonight, Tomorrow, This Weekend) and 9 category filters (Music, Nightlife, Culture, Food, Markets, Workshops, Meetups, Outdoors, Family)
- **Event Detail Cards** -- Venue, time, price, tags, description, and quick actions (Open in Maps, Save, Share)
- **User Accounts** -- Bookmarks, saved preferences, and taste profiles that learn from your queries

## Architecture

```
event-map/
├── web/                    # Next.js frontend (React 19, TypeScript, Tailwind)
│   ├── src/app/            # Pages and API routes
│   └── src/components/     # Map, filters, chat panel, event cards
├── scrapers/               # Python data pipeline (21 sources)
│   ├── *.py                # API and HTML scrapers
│   └── venues/             # Venue-specific scrapers
├── pipeline/               # Normalization, categorization, geocoding
├── db/                     # PostgreSQL schema and upsert logic
└── main.py                 # CLI entry point
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS, MapLibre GL |
| Database | Supabase (PostgreSQL + PostGIS) |
| Auth | Supabase Auth (email/password + Google OAuth) |
| AI | Claude Haiku (chat & categorization), Claude Sonnet (vision) |
| Scraping | Python 3.11, BeautifulSoup, Playwright, httpx |
| Hosting | Vercel (frontend), GitHub Actions (pipeline) |
| Geocoding | Nominatim (OpenStreetMap) + cached venue DB |

### Data Pipeline

Events are scraped daily at 2am UTC (4am Berlin) via GitHub Actions:

1. **Scrape** -- 21 sources: 3 public APIs (kulturdaten.berlin, Eventbrite, Meetup), 7 web scrapers (tip Berlin, berlin.de, Rausgegangen, Resident Advisor, Luma, Bandsintown, Berlin mit Kind), 11 venue-specific scrapers
2. **Normalize** -- Pydantic validation, date parsing, price extraction
3. **Categorize** -- 3-layer system: source tags -> keyword matching (3,000+ German/English terms) -> Claude Haiku LLM fallback. Layers 1+2 handle ~70-80% of events at zero LLM cost
4. **Geocode** -- 160+ hardcoded Berlin venues with Nominatim fallback
5. **Deduplicate & Upsert** -- SHA256 fingerprint on `lower(title) + date`, conflict resolution on insert

## Getting Started

### Prerequisites

- Node.js 18+
- Python 3.11
- Supabase project
- Anthropic API key

### Frontend

```bash
cd web
npm install
npm run dev
```

Create `web/.env.local`:

```
NEXT_PUBLIC_SUPABASE_URL=<your-supabase-url>
NEXT_PUBLIC_SUPABASE_ANON_KEY=<your-anon-key>
SUPABASE_SERVICE_KEY=<your-service-key>
ANTHROPIC_API_KEY=<your-api-key>
```

### Backend Pipeline

```bash
# Create and activate virtual environment
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .

# Install Playwright browsers (for JS-rendered pages)
playwright install chromium

# Run all scrapers
python main.py --run-all

# Run a single scraper
python main.py --run kulturdaten

# Dry run (no DB writes)
python main.py --run-all --dry-run

# List available scrapers
python main.py --list

# Start scheduler (continuous cron jobs)
python main.py
```

Create `.env`:

```
SUPABASE_URL=<your-supabase-url>
SUPABASE_SERVICE_KEY=<your-service-key>
ANTHROPIC_API_KEY=<your-api-key>
LOG_LEVEL=INFO
```

### Database

Apply the schema to your Supabase project:

```bash
python db/apply_schema.py
```

## License

All rights reserved.
