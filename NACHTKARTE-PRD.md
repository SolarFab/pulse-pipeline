# NachtKarte — Product Requirements Document (PRD)

## Berlin Real-Time Event Discovery App with AI Concierge

**Version:** 1.0 Draft
**Date:** March 11, 2026
**Author:** [Your Name]

---

## 1. Product Vision

**One-liner:** NachtKarte is an AI-powered, map-based event discovery app for Berlin that aggregates events from dozens of fragmented sources and lets users find what's happening through an interactive map, smart filters, or by simply chatting with an AI concierge.

**Tagline:** _"Your city's pulse, instantly."_

### The Problem

Berlin has one of the richest event scenes in the world, but discovering what's happening is frustratingly fragmented:

- Club nights live on Resident Advisor and Instagram stories
- Bar events exist only on individual bar websites or Facebook pages
- Cultural events are scattered across Tip Berlin, visitBerlin, kulturdaten.berlin
- To plan a spontaneous evening, you have to check 5–10 sources and scroll through endless lists
- No single tool gives you a **real-time, map-based, personalized** answer to: _"What should I do right now?"_

### The Solution

An AI-powered live map that:
1. **Crawls all Berlin event sources** automatically via AI agents (n8n pipelines)
2. **Displays events on a beautiful dark map** with category filters and time controls
3. **Lets you ask an AI concierge** in natural language: "I want to listen to jazz tonight" → instant personalized recommendations highlighted on the map
4. **Learns your taste** over time for better personalization

### Reference / Inspiration

The primary inspiration is **Ongeo** (NYC), a free iOS app that shows local events on a real-time map. See the reference screenshot below:

![Ongeo Reference - NYC event map app](./ongeo-reference.png)

Key things to take from Ongeo:
- Clean, map-first interface with event pins
- Time filter ("Within 2 hours") at the top
- Minimal UI, opens fast, works instantly
- No login required to browse

**Key differences for NachtKarte:**
- AI chat concierge (Ongeo doesn't have this)
- Deep personalization that learns your taste
- Berlin-specific with local sources (RA, Tip Berlin, etc.)
- Beyond nightlife: food, culture, wellness, markets, social events

### Competitive Landscape (March 2026)

| Feature | NachtKarte | THE CLUBMAP (just launched) | Ongeo (NYC only) | Resident Advisor |
|---|---|---|---|---|
| AI Concierge Chat | ✅ Core feature | ❌ | ❌ | ❌ |
| Personalization | Deep (learns taste) | Genre filters | Time filter only | Follow artists |
| Data Sources | All aggregated | Curated editorial | Web crawling | User submissions |
| Beyond Clubs | Everything | Clubs only | All categories | Music only |
| "Right Now" mode | ✅ Instant | Calendar-based | ✅ | Calendar-based |
| Map-first UX | ✅ | ✅ Map + Calendar | ✅ | List-based |
| Platform | iOS + Android + Web | iOS + Android | iOS only | Web + iOS + Android |

---

## 2. Target Users

### Primary: "Spontaneous Berliner" (age 22–40)
- Lives in Berlin, active social life
- Often doesn't know what to do on a given evening
- Tired of checking multiple sources
- Wants to discover things beyond their bubble
- Values curation over quantity

### Secondary: "Berlin Visitor" (tourists, new residents)
- Visiting or just moved to Berlin
- Overwhelmed by options
- Wants a local's perspective, not tourist traps
- Language barrier (needs English + German support)

### User Stories

1. **"I'm bored right now"** — Open app → see what's happening within walking distance in the next 2 hours → pick something → go
2. **"Plan tonight"** — Chat with AI: "Something chill with friends tonight, not too expensive" → get 3 curated suggestions on the map
3. **"Weekly explorer"** — Browse map filtered to "Culture" for the weekend → discover a gallery opening I'd never have found
4. **"Jazz lover"** — AI knows I love jazz → proactively shows me tonight's jazz events when I open the app
5. **"Group decision"** — Share a short list of AI-recommended events with friends via link

---

## 3. Core Features (MVP — v1.0)

### 3.1 Interactive Event Map

**Description:** A dark-themed, full-screen map of Berlin showing events as colored category pins. This is the default view when opening the app.

**Requirements:**
- Dark map tiles (Carto Dark Matter or Mapbox Dark)
- Events shown as colored emoji pins by category (see categories below)
- Tapping a pin opens an event detail card (bottom sheet)
- Pinch to zoom, pan to explore
- Cluster pins when zoomed out, expand when zoomed in
- "My location" button to center on user
- Smooth animations when filtering/highlighting events

**Event Categories & Colors:**
| Category | Emoji | Color | Examples |
|---|---|---|---|
| Music | 🎵 | `#e85d75` | Concerts, live jazz, DJ sets |
| Nightlife | 🌙 | `#8b5cf6` | Club nights, raves, bar parties |
| Food & Drink | 🍜 | `#f59e0b` | Street food markets, beer gardens, pop-ups |
| Culture & Art | 🎨 | `#06b6d4` | Gallery openings, museum nights, readings |
| Entertainment | 🎭 | `#ec4899` | Comedy, cinema, poetry slams, theater |
| Wellness | 🧘 | `#10b981` | Yoga, meditation, sports meetups |
| Social | 🎯 | `#f97316` | Meetups, game nights, language exchange |
| Markets | 🛍️ | `#a78bfa` | Flea markets, design markets, vintage |

### 3.2 Time & Category Filters

**Description:** Persistent filter bar at the top of the map that lets users control WHAT and WHEN they see.

**Time Filter Options:**
- **Right Now** — Events happening at this moment (default on app open)
- **Next 2 Hours** — Starting within 2 hours
- **Tonight** — From now until 6:00 AM
- **Today** — Full day
- **Tomorrow** — Tomorrow full day
- **This Weekend** — Friday 17:00 → Sunday 23:59
- **Pick a Date** — Calendar date picker
- **Pick a Time Range** — Custom start/end time selector

**Category Filters:**
- Horizontal scrollable pill buttons for each category
- Tap to toggle on/off (multiple can be active)
- "All" button to reset
- Active pills are colored, inactive are dimmed

**Neighborhood Filter (v1.1):**
- Optional: filter by Berlin Kiez (Kreuzberg, Mitte, Neukölln, etc.)

### 3.3 Event Detail Card

**Description:** Bottom sheet that slides up when tapping an event pin or list item.

**Fields to display:**
- Event title
- Venue name
- Category badge (emoji + label)
- Date & time (start – end)
- Neighborhood / Bezirk
- Price (Free / €X / "from €X")
- Short description (2-3 sentences)
- Tags (e.g., #jazz, #outdoor, #queer-friendly, #english)
- Source attribution ("via Resident Advisor", "via Tip Berlin")
- Action buttons:
  - "Open in Maps" → deep link to Apple Maps / Google Maps
  - "Save" → bookmark for later (local storage, no auth needed)
  - "Share" → native share sheet
  - "More Info" → open source URL in browser

### 3.4 AI Concierge (Chat)

**Description:** A conversational AI assistant accessible via the bottom navigation. The user can ask questions in natural language (German or English) and receive personalized event recommendations that are highlighted on the map.

**Requirements:**
- Chat interface with message bubbles (user = right, AI = left)
- Quick-prompt buttons shown on empty state:
  - "What's happening right now?"
  - "Jazz tonight?"
  - "Something free & spontaneous"
  - "Best techno tonight"
  - "Outdoor activities today"
  - "Something fun with friends"
- AI responses include event names that are tappable → opens event detail
- "Show on Map" button in AI responses → switches to map view with recommended events highlighted (pulsing pins)
- AI responds in the same language the user writes in
- AI has access to the full event database and gives opinionated, concierge-style recommendations (not just search results)
- Typing indicator (animated dots) while AI is thinking

**AI Behavior Rules:**
- Be a warm, opinionated local insider — have taste
- Recommend 1-3 events per response, explain WHY
- Add insider tips ("arrive before 22:00 to skip the line")
- Keep responses concise (2-4 sentences per recommendation)
- If nothing matches, suggest the closest alternative
- Remember context within the conversation

**Tech:** Claude API (claude-sonnet-4-20250514) with a system prompt containing the full event database. Events are referenced by ID so the frontend can highlight them.

### 3.5 Event List View

**Description:** Alternative to the map — a scrollable list of all visible events, sorted by time.

**Requirements:**
- List items show: category emoji, title, venue, neighborhood, time, price
- Tapping opens the event detail card
- Respects the same time & category filters as the map
- Sorted by start time (soonest first)
- Pull-to-refresh
- Search bar at top for keyword search

### 3.6 Bottom Navigation

Three tabs:
1. **🗺️ Map** — Interactive map (default)
2. **📋 Events** — List view
3. **✨ Ask AI** — Chat concierge

---

## 4. Data Architecture

### 4.1 Event Data Schema (Supabase / PostgreSQL)

```sql
CREATE TABLE events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  venue_name TEXT NOT NULL,
  venue_id UUID REFERENCES venues(id),
  
  -- Location
  lat DECIMAL(10, 7) NOT NULL,
  lng DECIMAL(10, 7) NOT NULL,
  neighborhood TEXT,             -- e.g., "Kreuzberg", "Mitte"
  address TEXT,
  
  -- Timing
  start_time TIMESTAMPTZ NOT NULL,
  end_time TIMESTAMPTZ,
  is_recurring BOOLEAN DEFAULT FALSE,
  recurrence_rule TEXT,          -- iCal RRULE format
  
  -- Classification
  category TEXT NOT NULL,        -- music, nightlife, food, culture, etc.
  subcategory TEXT,              -- jazz, techno, street food, gallery, etc.
  tags TEXT[],                   -- array of tags
  
  -- Details
  description TEXT,
  price TEXT,                    -- "Free", "€12", "from €8"
  price_cents INTEGER,           -- for sorting/filtering (0 = free)
  image_url TEXT,
  
  -- Source tracking
  source TEXT NOT NULL,          -- "resident_advisor", "tip_berlin", etc.
  source_url TEXT,               -- original event page URL
  source_id TEXT,                -- ID in source system (for dedup)
  
  -- Metadata
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  is_active BOOLEAN DEFAULT TRUE,
  quality_score DECIMAL(3,2),    -- AI-assigned quality/relevance score 0-1
  
  -- Deduplication
  fingerprint TEXT UNIQUE        -- hash of title+venue+date for dedup
);

CREATE TABLE venues (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  lat DECIMAL(10, 7) NOT NULL,
  lng DECIMAL(10, 7) NOT NULL,
  neighborhood TEXT,
  address TEXT,
  venue_type TEXT,               -- club, bar, gallery, park, etc.
  website_url TEXT,
  instagram_handle TEXT,
  google_place_id TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- PostGIS index for geospatial queries
CREATE INDEX events_location_idx ON events USING GIST (
  ST_SetSRID(ST_MakePoint(lng, lat), 4326)
);

-- Time-based index for "happening now" queries  
CREATE INDEX events_time_idx ON events (start_time, end_time);

-- Category index
CREATE INDEX events_category_idx ON events (category, is_active);
```

### 4.2 Key Queries

```sql
-- Events happening RIGHT NOW
SELECT * FROM events 
WHERE start_time <= NOW() 
  AND (end_time IS NULL OR end_time >= NOW())
  AND is_active = TRUE
ORDER BY start_time;

-- Events within 2km radius
SELECT *, ST_Distance(
  ST_SetSRID(ST_MakePoint(lng, lat), 4326),
  ST_SetSRID(ST_MakePoint(:user_lng, :user_lat), 4326)
) as distance
FROM events
WHERE ST_DWithin(
  ST_SetSRID(ST_MakePoint(lng, lat), 4326),
  ST_SetSRID(ST_MakePoint(:user_lng, :user_lat), 4326),
  0.02  -- ~2km in degrees
)
AND start_time <= :end_filter
AND (end_time IS NULL OR end_time >= :start_filter)
ORDER BY distance;
```

---

## 5. Event Data Sources & Scraping Pipeline

> **Note on tooling:** The pipeline is built as a Python project (no n8n). One module per source, shared normalizer, Claude API for extraction/categorization, APScheduler for cron jobs. See Section 5.3 for architecture.

### 5.1 Data Sources (Priority Order)

**Tier 1 — APIs (Structured, Start Here):**

| Source | What | Access | Schedule |
|---|---|---|---|
| **kulturdaten.berlin API** | Cultural events across all Berlin. Open government data. | FREE open API — `kulturdaten.readme.io` | Daily 6AM |
| **Eventbrite API** | Ticketed events: workshops, parties, markets, pop-ups | Free API key | Daily 6AM |
| **Meetup.com API** | Tech meetups, social groups, language exchange, community | Free API key | Daily 6AM |

**Tier 2 — Web Scraping (HTML/WordPress):**

| Source | What | Approach | Schedule |
|---|---|---|---|
| **Rausgegangen** (`rausgegangen.de/berlin`) | Best aggregator for local/underground — markets, pop-ups, curated daily picks | JSON-LD structured data present. Scrape event URLs, follow each for details. | 2x/day |
| **Tip Berlin** (`tip-berlin.de`) | Editorial curation, all categories. WordPress site. | WP REST API (`/wp-json/wp/v2/posts`) for pagination + metadata; parse HTML content for date/venue/price | Daily 6AM |
| **Berlin.de Events** | Official city calendar | BeautifulSoup, static HTML | Daily 6AM |
| **Resident Advisor** (`ra.co/events/de/berlin`) | Club nights, techno, DJ lineups | Playwright (JS-heavy, 403 on direct fetch). Rotate user-agents. | Daily 3AM |
| **visitBerlin.de** | Festivals, major events, tourism | Playwright + Drupal markup | Weekly |

**Tier 3 — Venue Direct Scrapers (High Quality, Low Noise):**

These venues have their own event pages and are the primary source for their events. Small effort per venue, very high signal.

| Venue | What | Why |
|---|---|---|
| **Markthalle Neun** | Street Food Thursday, Kinderflohmarkt, Schnippeldisko, community events | Custom CMS with JSON-LD, easy scrape |
| **Klunkerkranich** | Rooftop bar, culture nights, markets | Kreuzberg icon, distinct vibe |
| **Holzmarkt** | Bar25, community events, culture | Long-running creative community space |
| **Tresor** | Techno club program | Easier to scrape than RA, direct source |
| **Watergate** | Club nights | Direct source beats RA for their own events |
| **Sisyphos** | Weekend mega-parties | High search volume, worth direct scraping |
| **KitKat Club** | Parties, themed nights | Niche audience, high loyalty |
| **Nowkoelln Flowmarkt** | Maybachufer flea market, every 2nd Sunday | Static WordPress, grab recurring dates |
| **Mauerpark Flohmarkt** | Iconic Sunday flea market | Static site, easy |
| **Boxhagener Platz** | Sunday flea market, Friedrichshain | Static site |

**Tier 4 — Community Submissions (The "Cool Kids" Layer):**

See Section 5.4.

**Tier 5 — Social / Best-Effort:**

| Source | What | Notes |
|---|---|---|
| **Facebook Events** | Bar events, pop-ups, community events | Apify scraper — brittle, treat as bonus not core |
| **Instagram** (key venue accounts) | Pop-up announcements, DJ lineups | Not automatable reliably. Manual curation or Apify |

### 5.2 What Each Tier Solves

| Tier | Coverage | Vibe | Volume |
|---|---|---|---|
| APIs | Culture, workshops, community | Mainstream + local | High |
| Rausgegangen + Tip Berlin | Editorial picks | Curated, quality | Medium |
| Venue scrapers | Nightlife, markets, pop-ups | Authentic, local | Medium |
| Community submissions | Truly underground, pop-ups | Underground, unique | Low but gold |
| Social | Everything the rest misses | Raw, noisy | Very high |

### 5.3 Python Pipeline Architecture

```
event-map/
├── scrapers/
│   ├── base.py                 # BaseScraper: fetch(), normalize(), upsert()
│   ├── kulturdaten.py          # Tier 1: API
│   ├── eventbrite.py           # Tier 1: API
│   ├── meetup.py               # Tier 1: API
│   ├── rausgegangen.py         # Tier 2: JSON-LD + HTML
│   ├── tip_berlin.py           # Tier 2: WP REST API + HTML parse
│   ├── berlin_de.py            # Tier 2: BeautifulSoup
│   ├── resident_advisor.py     # Tier 2: Playwright
│   └── venues/
│       ├── markthalle_neun.py
│       ├── klunkerkranich.py
│       ├── holzmarkt.py
│       ├── nowkoelln.py        # Recurring schedule extrapolation
│       └── ...
├── pipeline/
│   ├── normalizer.py           # → unified Event schema
│   ├── deduplicator.py         # fingerprint: hash(title + venue + date)
│   ├── categorizer.py          # Claude API → category + tags
│   └── scheduler.py            # APScheduler cron jobs
├── db/
│   └── supabase.py             # upsert with conflict resolution
└── main.py
```

**Claude AI extraction prompt:**
```
Given this raw HTML/text from a Berlin event page, extract structured event data.

Return JSON with: title, venue_name, address, start_time (ISO 8601),
end_time, category (one of: music, nightlife, food, culture,
entertainment, wellness, social, market), subcategory, description
(2-3 sentences), price, tags (array of relevant tags).

If you cannot confidently extract a field, set it to null.
Assign a quality_score (0-1) based on how complete and reliable the data is.
```

### 5.4 Community Submissions

**The problem:** Pop-ups, one-night events, neighborhood happenings, and truly underground events are announced on Instagram and Facebook. They can't be reliably scraped.

**The solution:** A dead-simple submission form that feeds directly into Supabase with a `status = 'pending'` flag.

**Submission flow:**
```
User fills form (title, venue/address, date+time, category, description, URL)
    → Supabase: events table, status = 'pending', source = 'community'
    → Admin review queue (simple Supabase dashboard view or email notification)
    → Approve → status = 'active', appears on map
    → (v1.1) Auto-approve if user has trusted_submitter flag
```

**Form fields (minimal friction):**
- Event name *
- Date & time *
- Location / address *
- Category (dropdown) *
- Short description
- Link (Instagram post, Facebook event, website)
- Your name / Instagram (optional, for attribution)

**In the app:**
- Community-submitted events get a small "🙌 community pick" badge
- This signals authenticity and encourages more submissions
- Becomes a flywheel: locals submit → more locals discover → more locals submit

**Tech:** Google Form → Zapier/Make → Supabase (v0.1), or a custom `/submit` page in the web app (v1).

**Schema addition:**
```sql
-- Add to events table:
submitted_by TEXT,           -- optional name/handle
submission_link TEXT,        -- original Instagram/FB post URL
status TEXT DEFAULT 'active' -- 'active', 'pending', 'rejected'
```

---

## 6. Tech Stack

| Layer | Tool | Why |
|---|---|---|
| **Frontend (Production)** | React Native + Expo | One codebase → iOS + Android + Web. Expo EAS for builds. |
| **Frontend (Prototype)** | Lovable.dev or Bolt.new | Rapid UI iteration. Export code when ready. |
| **Maps** | Mapbox GL or MapLibre GL | Beautiful dark tiles, clustering, smooth animations. MapLibre = free. |
| **Database** | Supabase (PostgreSQL + PostGIS) | Free tier, real-time, geospatial queries, auth, storage. |
| **AI Agent Pipeline** | n8n (cloud or self-hosted) | Event scraping, data cleaning, scheduling. Already connected. |
| **AI Concierge** | Claude API (Anthropic) | Conversational recommendations. Sonnet for speed. |
| **Hosting (Web)** | Vercel | Free tier, great DX, instant deploys. |
| **Hosting (Apps)** | Expo EAS | Build & submit iOS/Android from cloud. |
| **Analytics** | PostHog | Open-source, privacy-first. Self-hostable. |
| **Error Tracking** | Sentry | Free tier, essential for production. |

---

## 7. Development Phases

### Phase 1: Working Prototype (Weeks 1–3)

**Goal:** A functional web app with real event data and AI chat.

- [ ] Set up Supabase project with events + venues tables
- [ ] Build n8n workflow for kulturdaten.berlin API → Supabase
- [ ] Build n8n workflow for Eventbrite API → Supabase
- [ ] Build frontend in Lovable/Bolt: map + filters + event detail + AI chat
- [ ] Connect Claude API for the concierge
- [ ] Seed 200+ real Berlin events
- [ ] Deploy web app on Vercel
- [ ] Test with 5 friends

### Phase 2: Data Expansion (Weeks 4–6)

**Goal:** Comprehensive event coverage for Berlin.

- [ ] Build RA scraper (Python via n8n)
- [ ] Build Tip Berlin scraper
- [ ] Build berlin.de scraper
- [ ] Add deduplication logic (fingerprint matching)
- [ ] Add AI-powered categorization and quality scoring
- [ ] Reach 500+ events per week
- [ ] Add "Right Now" and time range filters
- [ ] Add neighborhood filter

### Phase 3: Mobile App (Weeks 7–10)

**Goal:** Native iOS + Android app.

- [ ] Port frontend to React Native + Expo
- [ ] Implement native map (Mapbox RN SDK)
- [ ] Push notifications ("Jazz night near you in 1 hour!")
- [ ] Bookmarks / saved events (local storage)
- [ ] Submit to App Store + Google Play
- [ ] TestFlight / beta distribution

### Phase 4: Personalization & Growth (Weeks 11–16)

**Goal:** AI learns user preferences, viral growth features.

- [ ] User accounts (Supabase Auth, optional)
- [ ] Track event taps, saves, AI queries → build taste profile
- [ ] Personalized "For You" feed on map open
- [ ] Share event lists with friends (link)
- [ ] "Tonight" widget for iOS
- [ ] Instagram/TikTok marketing content
- [ ] Track weekly active users, retention

---

## 8. Monetization (Future)

| Model | Description | Timeline |
|---|---|---|
| **Freemium** | Free for all users. Premium for advanced filters, no ads. | v2.0 |
| **Venue Promotion** | Venues pay to boost their events on the map (highlighted pin). | v2.0 |
| **Affiliate Tickets** | Commission on tickets sold via Eventbrite/Dice/RA links. | v1.5 |
| **Sponsored Recommendations** | AI concierge subtly includes sponsored venues (labeled). | v3.0 |
| **Data Insights** | Sell anonymized trend data to venues/promoters. | v3.0 |

---

## 9. Success Metrics (MVP)

| Metric | Target (Month 1) | Target (Month 3) |
|---|---|---|
| Weekly Active Users | 200 | 2,000 |
| Events in Database | 500/week | 2,000/week |
| AI Chat Sessions / Week | 100 | 1,000 |
| Data Sources Connected | 3–4 | 8–10 |
| App Store Rating | — | 4.5+ |
| Avg. Session Duration | 2+ min | 3+ min |

---

## 10. Design Principles

1. **Map-first, always.** The map is the hero. Everything else is secondary.
2. **Instant value.** Open the app → see what's happening. No onboarding, no login, no friction.
3. **Opinionated AI.** The concierge has taste. It doesn't just list events — it recommends with conviction.
4. **Dark & clean.** Dark theme (matches nightlife context), minimal chrome, content-forward.
5. **Berlin-authentic.** This app should feel like it was made BY Berliners FOR Berliners. No tourist-trap vibes.
6. **Privacy-first.** No login required for core features. Location used only when app is open. No tracking beyond essential analytics.

---

## 11. Open Questions

- [ ] Should the AI concierge have a name/persona? (e.g., "Nacht" or "Karte")
- [ ] How to handle events that span multiple days (festivals)?
- [ ] Should we allow user-submitted events in v1?
- [ ] Partnering with THE CLUBMAP for data sharing (they're building an API)?
- [ ] Should we open-source the scraping pipeline?

---

## 12. References

- **Ongeo App (inspiration):** https://ongeo.app — NYC event discovery on a map
- **THE CLUBMAP (Berlin competitor, just launched):** Berlin nightlife calendar with map + app
- **kulturdaten.berlin API:** https://kulturdaten.readme.io — Free Berlin cultural data API
- **RA Scraper (GitHub):** https://github.com/djb-gt/resident-advisor-events-scraper
- **NachtKarte Prototype (Claude artifact):** See attached `nachtkarte-berlin.jsx`
