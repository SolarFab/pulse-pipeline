#!/usr/bin/env python3
"""
Analyze NachtKarte events to propose subcategories for the 9-category taxonomy.
Fetches all events from Supabase, assigns new categories, analyzes tags,
and proposes subcategories via tag clustering.
"""

import os, sys, json
from collections import Counter, defaultdict
from supabase import create_client

# --- Config ---
SUPABASE_URL = "https://ykkjhmohqibepqovtjqs.supabase.co"
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
PAGE_SIZE = 1000

NEW_CATEGORIES = [
    "Music", "Nightlife", "Culture", "Food", "Markets",
    "Meetups", "Workshops", "Outdoors", "Family"
]

# kulturdaten source_tags -> new category
KULTURDATEN_MAP = {
    "music": "Music",
    "exhibitions": "Culture",
    "art": "Culture",
    "stages": "Culture",
    "children": "Family",
    "education": "Workshops",
    "informationevents": "Meetups",
    "politics": "Meetups",
    "women": "Meetups",
    "conferences": "Meetups",
    "lectures": "Meetups",
    "health": "Meetups",
    "recreation": "Workshops",
    "walks": "Outdoors",
    "dance": "Workshops",
    "festivals": "Culture",
    "weeklymarkets": "Markets",
    "christmastime": "Markets",
    "seniors": "Workshops",
    "police": "EXCLUDE",
}

# Other sources: existing category -> new category
OTHER_SOURCE_MAP = {
    "music": "Music",
    "nightlife": "Nightlife",
    "culture": "Culture",
    "food": "Food",
    "market": "Markets",
    "social": "Meetups",
    "wellness": "Outdoors",
    "entertainment": "Culture",
}


def fetch_all_events(sb):
    """Paginate through all events, 1000 per page."""
    all_events = []
    offset = 0
    while True:
        resp = (
            sb.table("events")
            .select("source, tags, source_tags, title, venue_name, category")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        batch = resp.data
        if not batch:
            break
        all_events.extend(batch)
        print(f"  Fetched {len(all_events)} events so far...")
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return all_events


def assign_new_category(event):
    """Return the new category for an event, or None if excluded."""
    source = (event.get("source") or "").lower().strip()
    source_tags = event.get("source_tags") or []
    old_cat = (event.get("category") or "").lower().strip()

    if source == "kulturdaten":
        # Use first matching source_tag
        for st in source_tags:
            key = st.lower().strip()
            if key in KULTURDATEN_MAP:
                mapped = KULTURDATEN_MAP[key]
                if mapped == "EXCLUDE":
                    return None
                return mapped
        # Fallback: try old category mapping
        if old_cat in OTHER_SOURCE_MAP:
            return OTHER_SOURCE_MAP[old_cat]
        return "Culture"  # default for kulturdaten
    else:
        if old_cat in OTHER_SOURCE_MAP:
            return OTHER_SOURCE_MAP[old_cat]
        # Unmapped category
        return None


def normalize_tag(t):
    """Lowercase, strip whitespace."""
    return t.strip().lower()


def extract_tags(event):
    """Get normalized tags from an event."""
    raw = event.get("tags") or []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = [raw]
    return [normalize_tag(t) for t in raw if t and normalize_tag(t)]


# --- Subcategory clustering definitions (manual semantic grouping) ---
# These will be applied after seeing the actual tag distributions.
# We define broad keyword-based clusters per category.

SUBCATEGORY_RULES = {
    "Culture": {
        "Visual Arts & Exhibitions": ["exhibition", "gallery", "painting", "sculpture", "photography", "visual", "art", "installation", "museum", "contemporary art", "fine art", "illustration", "drawing", "graphic", "print"],
        "Theater & Performing Arts": ["theater", "theatre", "stage", "drama", "performance", "performing", "improv", "cabaret", "burlesque", "circus", "puppet", "comedy", "stand-up", "standup"],
        "Film & Cinema": ["film", "cinema", "movie", "screening", "documentary", "short film", "animation"],
        "Literature & Readings": ["reading", "book", "literature", "poetry", "author", "literary", "novel", "writing"],
        "Festivals & Cultural Events": ["festival", "cultural", "culture", "celebration", "heritage", "tradition", "international"],
        "Design & Architecture": ["design", "architecture", "fashion", "craft", "ceramics", "textile", "jewelry"],
    },
    "Music": {
        # Will be handled specially - genre vs format
    },
    "Nightlife": {
        "Club Nights & DJ Sets": ["club", "dj", "techno", "house", "electronic", "bass", "drum and bass", "dnb", "trance", "rave", "dance floor", "afterhour", "minimal"],
        "Bar Events & Cocktails": ["bar", "cocktail", "drink", "happy hour", "pub", "lounge"],
        "Karaoke & Party Games": ["karaoke", "quiz", "trivia", "game", "bingo", "party"],
        "Late Night & Special": ["late night", "midnight", "drag", "burlesque", "variety", "open format"],
    },
    "Food": {
        "Street Food & Food Trucks": ["street food", "food truck", "food market", "food stand", "fast food", "burger", "pizza", "döner"],
        "Fine Dining & Tastings": ["tasting", "wine", "beer", "cocktail", "fine dining", "gourmet", "culinary", "chef", "sommelier", "whisky", "whiskey"],
        "Cooking & Food Workshops": ["cooking", "baking", "recipe", "kitchen", "culinary class", "food workshop"],
        "Brunch & Cafe Culture": ["brunch", "breakfast", "cafe", "coffee", "bakery", "pastry"],
        "Cultural & Regional Cuisine": ["vegan", "vegetarian", "thai", "italian", "japanese", "indian", "mexican", "korean", "vietnamese", "turkish", "middle eastern", "african"],
    },
    "Markets": {
        "Flea Markets & Vintage": ["flea", "vintage", "antique", "secondhand", "second-hand", "thrift", "retro", "trödel"],
        "Weekly & Farmers Markets": ["weekly", "farmer", "organic", "bio", "fresh", "produce", "wochenmarkt"],
        "Christmas & Seasonal Markets": ["christmas", "weihnacht", "holiday", "seasonal", "winter", "advent", "easter", "spring"],
        "Art & Design Markets": ["art market", "design market", "craft market", "handmade", "maker", "artisan", "kunstmarkt"],
    },
    "Meetups": {
        "Tech & Startup": ["tech", "startup", "coding", "programming", "software", "developer", "hackathon", "data", "ai", "machine learning", "blockchain", "crypto", "web", "app", "digital"],
        "Networking & Professional": ["networking", "professional", "business", "entrepreneur", "career", "conference", "panel", "talk", "speaker", "presentation", "seminar"],
        "Community & Social": ["community", "social", "meetup", "group", "gathering", "volunteer", "charity", "activism", "political", "feminist", "queer", "lgbtq", "inclusion", "diversity"],
        "Language & Cultural Exchange": ["language", "tandem", "exchange", "international", "expat", "english", "german", "spanish", "french", "conversation"],
        "Sustainability & Urban": ["sustainability", "climate", "environment", "green", "urban", "garden", "eco", "zero waste", "recycling"],
    },
    "Workshops": {
        "Art & Creative": ["art", "painting", "drawing", "sculpture", "ceramics", "pottery", "craft", "creative", "watercolor", "printmaking", "illustration", "calligraphy", "diy"],
        "Dance & Movement": ["dance", "salsa", "tango", "swing", "bachata", "ballet", "contemporary dance", "hip-hop dance", "lindy hop", "contact improv", "movement", "choreography"],
        "Wellness & Mindfulness": ["yoga", "meditation", "mindfulness", "wellness", "healing", "breathwork", "sound bath", "relaxation", "self-care", "therapy", "holistic"],
        "Education & Skills": ["workshop", "class", "course", "learn", "training", "skill", "education", "lecture", "seminar", "tutorial"],
        "Music & Production": ["music production", "djing", "instrument", "guitar", "piano", "singing", "vocal", "songwriting", "beat"],
    },
    "Outdoors": {
        "Walking & Hiking Tours": ["walk", "walking", "hike", "hiking", "tour", "guided", "stadtführung", "kiez", "neighborhood", "explore"],
        "Sports & Fitness": ["sport", "fitness", "run", "running", "cycling", "bike", "swim", "climbing", "basketball", "football", "soccer", "volleyball", "skating", "outdoor fitness"],
        "Parks & Nature": ["park", "garden", "nature", "lake", "river", "forest", "green", "picnic", "botanical"],
        "Water & Beach": ["boat", "kayak", "canoe", "paddle", "beach", "spree", "river cruise", "swimming"],
    },
    "Family": {
        "Kids Activities & Play": ["kids", "children", "child", "play", "playground", "toddler", "baby", "family", "kindertheater"],
        "Educational & Museums": ["museum", "science", "learn", "education", "workshop", "experiment", "discovery"],
        "Outdoor & Nature for Families": ["park", "zoo", "farm", "garden", "nature", "outdoor", "picnic", "animal"],
        "Shows & Entertainment": ["show", "circus", "puppet", "magic", "theater", "theatre", "performance", "story", "storytelling", "clown"],
    },
}

# Music special handling: genre vs format
MUSIC_GENRES = {
    "Electronic & DJ": ["electronic", "techno", "house", "ambient", "edm", "electro", "synth", "minimal", "deep house", "tech house", "trance", "drum and bass", "dnb", "dubstep", "breakbeat", "downtempo", "idm", "experimental electronic"],
    "Jazz & Blues": ["jazz", "blues", "swing", "bebop", "fusion", "smooth jazz", "free jazz", "nu jazz", "soul jazz", "big band"],
    "Classical & Contemporary Classical": ["classical", "orchestra", "symphony", "chamber", "opera", "choir", "choral", "baroque", "romantic", "contemporary classical", "new music", "ensemble", "piano recital", "string quartet"],
    "Rock & Alternative": ["rock", "alternative", "indie", "punk", "metal", "grunge", "post-punk", "shoegaze", "garage", "psychedelic", "hardcore", "emo", "noise"],
    "Hip-Hop & R&B": ["hip-hop", "hip hop", "rap", "r&b", "rnb", "trap", "grime", "boom bap", "neo soul", "afrobeat"],
    "Pop & Singer-Songwriter": ["pop", "singer-songwriter", "singer songwriter", "indie pop", "synth pop", "dream pop", "folk pop", "acoustic"],
    "World & Folk": ["world", "folk", "latin", "reggae", "ska", "afro", "african", "arabic", "balkan", "klezmer", "celtic", "flamenco", "bossa nova", "samba", "cumbia", "dub", "roots"],
    "Experimental & Avant-Garde": ["experimental", "avant-garde", "noise", "sound art", "improvisation", "free improv", "drone", "field recording", "musique concrète"],
}

MUSIC_FORMATS = {
    "Live Concerts": ["live", "concert", "gig", "performance", "band", "live music", "show", "recital"],
    "DJ Sets & Club Nights": ["dj", "dj set", "club", "club night", "set", "b2b", "vinyl"],
    "Open Mic & Jam Sessions": ["open mic", "jam", "jam session", "open stage", "unplugged"],
    "Festivals & Multi-Day": ["festival", "open air", "outdoor", "multi-day", "lineup"],
    "Listening Sessions & Releases": ["listening", "album", "release", "premiere", "launch", "listening session", "record"],
}


def match_subcategory(tag, rules):
    """Check if a tag matches any keyword in any subcategory rule."""
    matches = []
    for subcat, keywords in rules.items():
        for kw in keywords:
            if kw in tag or tag in kw:
                matches.append(subcat)
                break
    return matches


def analyze_music_special(events_by_cat):
    """Special analysis for Music category: genres vs formats."""
    music_events = events_by_cat.get("Music", [])
    all_tags = Counter()
    for ev in music_events:
        for t in extract_tags(ev):
            all_tags[t] += 1

    print("\n" + "=" * 80)
    print("MUSIC CATEGORY - SPECIAL ANALYSIS")
    print("=" * 80)
    print(f"\nTotal music events: {len(music_events)}")
    print(f"Unique tags: {len(all_tags)}")

    # Show top 40 tags
    print("\nTop 40 music tags:")
    for i, (tag, count) in enumerate(all_tags.most_common(40), 1):
        print(f"  {i:2d}. {tag:<40s} ({count})")

    # Genre analysis
    print("\n--- GENRE SUBCATEGORIES ---")
    genre_counts = {}
    genre_tag_details = {}
    for genre, keywords in MUSIC_GENRES.items():
        matched_tags = Counter()
        for tag, count in all_tags.items():
            for kw in keywords:
                if kw in tag or tag in kw:
                    matched_tags[tag] = count
                    break
        total = sum(matched_tags.values())
        genre_counts[genre] = total
        genre_tag_details[genre] = matched_tags

    for genre in sorted(genre_counts, key=genre_counts.get, reverse=True):
        total = genre_counts[genre]
        if total < 5:
            continue
        tags = genre_tag_details[genre]
        top_tags = ", ".join(f"{t}({c})" for t, c in tags.most_common(8))
        marker = " [KEEP]" if total >= 20 else " [LOW]"
        print(f"  {genre:<40s} ~{total:>5d} events{marker}")
        print(f"    Tags: {top_tags}")

    # Format analysis
    print("\n--- FORMAT SUBCATEGORIES ---")
    format_counts = {}
    format_tag_details = {}
    for fmt, keywords in MUSIC_FORMATS.items():
        matched_tags = Counter()
        for tag, count in all_tags.items():
            for kw in keywords:
                if kw in tag or tag in kw:
                    matched_tags[tag] = count
                    break
        total = sum(matched_tags.values())
        format_counts[fmt] = total
        format_tag_details[fmt] = matched_tags

    for fmt in sorted(format_counts, key=format_counts.get, reverse=True):
        total = format_counts[fmt]
        if total < 5:
            continue
        tags = format_tag_details[fmt]
        top_tags = ", ".join(f"{t}({c})" for t, c in tags.most_common(8))
        marker = " [KEEP]" if total >= 20 else " [LOW]"
        print(f"  {fmt:<40s} ~{total:>5d} events{marker}")
        print(f"    Tags: {top_tags}")

    return genre_counts, format_counts


def main():
    print("Connecting to Supabase...")
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    print("Fetching all events...")
    events = fetch_all_events(sb)
    print(f"\nTotal events fetched: {len(events)}")

    # --- Step 2: Assign new categories ---
    print("\n" + "=" * 80)
    print("STEP 2: CATEGORY ASSIGNMENT")
    print("=" * 80)

    events_by_cat = defaultdict(list)
    excluded = 0
    unmapped = 0
    source_counts = Counter()

    for ev in events:
        source_counts[ev.get("source", "unknown")] += 1
        new_cat = assign_new_category(ev)
        if new_cat is None:
            excluded += 1
            continue
        events_by_cat[new_cat].append(ev)

    print(f"\nSource distribution:")
    for src, cnt in source_counts.most_common():
        print(f"  {src}: {cnt}")

    print(f"\nCategory assignment results:")
    total_assigned = 0
    for cat in NEW_CATEGORIES:
        cnt = len(events_by_cat[cat])
        total_assigned += cnt
        print(f"  {cat:<15s}: {cnt:>6d}")
    print(f"  {'EXCLUDED':<15s}: {excluded:>6d}")
    print(f"  {'TOTAL':<15s}: {total_assigned + excluded:>6d}")

    # --- Step 3: Tag analysis per category ---
    print("\n" + "=" * 80)
    print("STEP 3: TOP 40 TAGS PER CATEGORY")
    print("=" * 80)

    cat_tag_counters = {}
    for cat in NEW_CATEGORIES:
        tag_counter = Counter()
        for ev in events_by_cat[cat]:
            for t in extract_tags(ev):
                tag_counter[t] += 1
        cat_tag_counters[cat] = tag_counter

        print(f"\n--- {cat} ({len(events_by_cat[cat])} events, {len(tag_counter)} unique tags) ---")
        for i, (tag, count) in enumerate(tag_counter.most_common(40), 1):
            print(f"  {i:2d}. {tag:<45s} ({count})")

    # --- Step 4: Propose subcategories ---
    print("\n" + "=" * 80)
    print("STEP 4: PROPOSED SUBCATEGORIES")
    print("=" * 80)

    all_subcats = {}  # cat -> list of (subcat_name, count, top_tags)

    for cat in NEW_CATEGORIES:
        if cat == "Music":
            continue  # handled separately

        rules = SUBCATEGORY_RULES.get(cat, {})
        if not rules:
            print(f"\n--- {cat}: No subcategory rules defined ---")
            continue

        tag_counter = cat_tag_counters[cat]
        subcat_results = []

        print(f"\n--- {cat} ---")
        for subcat_name, keywords in rules.items():
            matched_tags = Counter()
            for tag, count in tag_counter.items():
                for kw in keywords:
                    if kw in tag or tag in kw:
                        matched_tags[tag] = count
                        break
            total = sum(matched_tags.values())
            if total >= 20:
                top = ", ".join(f"{t}({c})" for t, c in matched_tags.most_common(6))
                print(f"  {subcat_name:<40s} ~{total:>5d} events")
                print(f"    Top tags: {top}")
                subcat_results.append((subcat_name, total, matched_tags.most_common(6)))
            elif total > 0:
                print(f"  {subcat_name:<40s} ~{total:>5d} events [BELOW THRESHOLD]")

        all_subcats[cat] = subcat_results

    # --- Step 5: Music special ---
    genre_counts, format_counts = analyze_music_special(events_by_cat)

    # Build music subcats for summary
    music_genre_subcats = [(g, c) for g, c in genre_counts.items() if c >= 20]
    music_format_subcats = [(f, c) for f, c in format_counts.items() if c >= 20]

    # --- Step 6: Final summary ---
    print("\n" + "=" * 80)
    print("STEP 6: FINAL SUMMARY TABLE")
    print("=" * 80)
    print(f"\n{'Category':<15s} {'Events':>7s}  {'Subcategories'}")
    print("-" * 80)

    for cat in NEW_CATEGORIES:
        total_ev = len(events_by_cat[cat])
        if cat == "Music":
            subcats_str = "GENRES: " + ", ".join(
                f"{g}(~{c})" for g, c in sorted(music_genre_subcats, key=lambda x: -x[1]) if c >= 20
            )
            subcats_str += " | FORMATS: " + ", ".join(
                f"{f}(~{c})" for f, c in sorted(music_format_subcats, key=lambda x: -x[1]) if c >= 20
            )
            # Wrap long lines
            lines = [subcats_str[i:i+60] for i in range(0, len(subcats_str), 60)]
            print(f"{cat:<15s} {total_ev:>7d}  {lines[0]}")
            for line in lines[1:]:
                print(f"{'':>24s}{line}")
        else:
            subcats = all_subcats.get(cat, [])
            if subcats:
                subcats_sorted = sorted(subcats, key=lambda x: -x[1])
                subcat_strs = [f"{s[0]}(~{s[1]})" for s in subcats_sorted]
                line = ", ".join(subcat_strs)
                # Wrap
                parts = []
                current = ""
                for s in subcat_strs:
                    if current and len(current) + len(s) + 2 > 58:
                        parts.append(current)
                        current = s
                    else:
                        current = current + ", " + s if current else s
                if current:
                    parts.append(current)
                print(f"{cat:<15s} {total_ev:>7d}  {parts[0]}")
                for p in parts[1:]:
                    print(f"{'':>24s}{p}")
            else:
                print(f"{cat:<15s} {total_ev:>7d}  (no subcategories proposed)")

    print("\n" + "=" * 80)
    print("DONE")
    print("=" * 80)


if __name__ == "__main__":
    main()
