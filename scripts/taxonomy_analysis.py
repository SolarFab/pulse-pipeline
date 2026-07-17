"""
NachtKarte Taxonomy Analysis Script
Maps existing event data to the new 8-category taxonomy.
"""

import os
import sys
import json
from collections import Counter, defaultdict

import requests
from dotenv import load_dotenv

load_dotenv("/Users/solarlord/Projects/event-map/.env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}
TABLE_URL = f"{SUPABASE_URL}/rest/v1/events"

# ── New 8-category taxonomy ──────────────────────────────────────────
NEW_CATEGORIES = [
    "Music", "Nightlife", "Arts & Culture", "Food & Drink",
    "Markets", "Community", "Outdoors", "Family",
]

# ── Step 1: Fetch ALL events with pagination ─────────────────────────
def fetch_all_events():
    """Fetch all events using Range header pagination, 1000 per page."""
    all_events = []
    page = 0
    page_size = 1000
    select_cols = "source,category,tags,source_tags,title,venue_name,description"

    while True:
        start = page * page_size
        end = start + page_size - 1
        resp = requests.get(
            TABLE_URL,
            headers={
                **HEADERS,
                "Range": f"{start}-{end}",
                "Prefer": "count=exact",
            },
            params={"select": select_cols},
        )
        if resp.status_code not in (200, 206):
            print(f"Error fetching page {page}: {resp.status_code} {resp.text}")
            break

        data = resp.json()
        if not data:
            break
        all_events.extend(data)
        print(f"  Fetched page {page}: {len(data)} events (total so far: {len(all_events)})")

        # If we got fewer than page_size, we're done
        if len(data) < page_size:
            break
        page += 1

    return all_events


def main():
    print("=" * 80)
    print("NACHTKARTE TAXONOMY ANALYSIS")
    print("=" * 80)

    print("\n>> Fetching all events from Supabase...")
    events = fetch_all_events()
    print(f"\nTotal events fetched: {len(events)}")

    # Split by source
    by_source = defaultdict(list)
    for e in events:
        by_source[e.get("source", "unknown")].append(e)

    print("\n── Events by source ──")
    for src, evts in sorted(by_source.items(), key=lambda x: -len(x[1])):
        print(f"  {src:25s} {len(evts):>6,}")

    # ─────────────────────────────────────────────────────────────────
    # PART A: Map kulturdaten source_tags
    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("PART A: KULTURDATEN SOURCE_TAG MAPPING")
    print("=" * 80)

    kd_events = by_source.get("kulturdaten", [])
    print(f"\nKulturdaten events: {len(kd_events)}")

    # Count source_tags (strip the "attraction.category." prefix)
    kd_tag_counter = Counter()
    kd_tag_events = defaultdict(list)
    for e in kd_events:
        stags = e.get("source_tags") or []
        if isinstance(stags, str):
            stags = [stags]
        cleaned = []
        for t in stags:
            t_clean = t.replace("attraction.category.", "")
            kd_tag_counter[t_clean] += 1
            kd_tag_events[t_clean].append(e)
            cleaned.append(t_clean)
        e["_clean_source_tags"] = cleaned

    print("\nKulturdaten source_tags distribution:")
    for tag, count in kd_tag_counter.most_common():
        print(f"  {tag:25s} {count:>6,}")

    # Definite mappings
    DEFINITE_MAP = {
        "Exhibitions": "Arts & Culture",
        "Children": "Family",
        "Education": "Community",
        "InformationEvents": "Community",
        "Politics": "Community",
        "Lectures": "Community",
        "Music": "Music",
        "Walks": "Outdoors",
        "Women": "Community",
        "Seniors": "Community",
        "WeeklyMarkets": "Markets",
        "Conferences": "Community",
        "Art": "Arts & Culture",
        "ChristmasTime": "Markets",
    }

    # Ambiguous tags — print samples
    AMBIGUOUS = ["Recreation", "Festivals", "Police", "Stages", "Dance", "Health"]

    print("\n── Samples for AMBIGUOUS kulturdaten source_tags ──")
    for tag in AMBIGUOUS:
        sample = kd_tag_events.get(tag, [])[:15]
        print(f"\n  [{tag}] ({kd_tag_counter.get(tag, 0)} total)")
        for e in sample:
            title = (e.get("title") or "")[:80]
            venue = (e.get("venue_name") or "")[:30]
            print(f"    - {title}  @ {venue}")
        if not sample:
            print("    (no events)")

    # ─────────────────────────────────────────────────────────────────
    # PART B: Non-kulturdaten tag analysis
    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("PART B: NON-KULTURDATEN TAG ANALYSIS")
    print("=" * 80)

    non_kd_sources = [
        "tip_berlin", "rausgegangen", "luma", "jazzclubs",
        "eventbrite", "meetup", "resident_advisor", "planetarium",
    ]

    # Collect all tags
    tag_counter = Counter()
    tag_source = defaultdict(set)      # tag -> set of sources it appears in
    tag_events_map = defaultdict(list)  # tag -> list of events

    for src in non_kd_sources:
        for e in by_source.get(src, []):
            tags = e.get("tags") or []
            if isinstance(tags, str):
                tags = [tags]
            for t in tags:
                t_clean = t.strip()
                if t_clean:
                    tag_counter[t_clean] += 1
                    tag_source[t_clean].add(src)
                    tag_events_map[t_clean].append(e)

    # Also consider category field
    cat_counter = Counter()
    for src in non_kd_sources:
        for e in by_source.get(src, []):
            cat = e.get("category")
            if cat:
                cat_counter[cat] += 1

    print(f"\nUnique tags across non-kulturdaten sources: {len(tag_counter)}")
    print(f"Tags appearing 5+ times: {sum(1 for c in tag_counter.values() if c >= 5)}")

    print("\nExisting category values (non-kulturdaten):")
    for cat, count in cat_counter.most_common():
        print(f"  {cat:35s} {count:>6,}")

    # Heuristic mapping of tags to new categories
    TAG_KEYWORD_MAP = {
        "Music": [
            "music", "jazz", "concert", "live music", "dj", "electronic",
            "techno", "house", "hip hop", "hip-hop", "classical", "orchestra",
            "piano", "guitar", "band", "singer", "songwriter", "opera",
            "funk", "soul", "reggae", "punk", "rock", "metal", "blues",
            "ambient", "experimental music", "sound", "beats", "vinyl",
            "synth", "bass", "drum", "acoustic", "choir", "vocal",
            "rap", "r&b", "rnb", "indie", "pop", "afrobeat", "latin",
            "salsa music", "bossa nova", "cumbia",
        ],
        "Nightlife": [
            "nightlife", "club", "clubbing", "party", "nightclub", "rave",
            "afterparty", "after-party", "bar", "cocktail", "drinks",
            "dance party", "dancefloor", "dance floor", "dancing",
            "drag", "queer party", "fetish", "kink", "burlesque",
            "karaoke", "pub crawl",
        ],
        "Arts & Culture": [
            "art", "exhibition", "gallery", "museum", "theater", "theatre",
            "performance", "film", "cinema", "movie", "photography",
            "painting", "sculpture", "installation", "design", "architecture",
            "literature", "poetry", "reading", "book", "culture",
            "contemporary art", "modern art", "visual art", "digital art",
            "street art", "illustration", "print", "craft", "ceramic",
            "textile", "fashion", "dance performance", "ballet", "comedy",
            "stand-up", "standup", "improv", "open mic",
        ],
        "Food & Drink": [
            "food", "drink", "restaurant", "dining", "cooking", "culinary",
            "wine", "beer", "brewery", "tasting", "brunch", "lunch",
            "dinner", "supper club", "food market", "street food",
            "vegan", "vegetarian", "baking",
        ],
        "Markets": [
            "market", "flea market", "christmas market", "weihnachtsmarkt",
            "craft market", "vintage", "handmade", "makers", "bazaar",
            "fair", "farmers market", "antique",
        ],
        "Community": [
            "community", "workshop", "meetup", "networking", "social",
            "talk", "discussion", "panel", "conference", "seminar",
            "lecture", "education", "class", "course", "training",
            "language", "tech", "startup", "coding", "programming",
            "hackathon", "coworking", "entrepreneur", "business",
            "meditation", "yoga", "wellness", "mindfulness", "spiritual",
            "volunteering", "activism", "protest", "political", "fundraiser",
            "charity", "lgbtq", "queer", "feminist", "women",
            "expat", "international", "multicultural",
        ],
        "Outdoors": [
            "outdoor", "outdoors", "nature", "park", "garden", "hike",
            "hiking", "bike", "cycling", "running", "sports", "fitness",
            "swim", "lake", "river", "picnic", "bbq", "camping",
            "walk", "walking tour", "boat", "kayak",
        ],
        "Family": [
            "family", "kids", "children", "child", "baby", "toddler",
            "parent", "kid-friendly", "family-friendly", "puppet",
            "circus", "magic show", "planetarium", "science",
        ],
    }

    def classify_tag(tag):
        """Classify a tag into one of the 8 categories using keyword matching."""
        t_lower = tag.lower()
        scores = Counter()
        for cat, keywords in TAG_KEYWORD_MAP.items():
            for kw in keywords:
                if kw in t_lower or t_lower in kw:
                    scores[cat] += 1
        if scores:
            return scores.most_common(1)[0][0]
        return None

    # Build mapping for tags with 5+ occurrences
    frequent_tags = [(tag, count) for tag, count in tag_counter.most_common() if count >= 5]

    by_new_cat = defaultdict(list)  # new_cat -> list of (tag, count)
    unmapped_tags = []

    for tag, count in frequent_tags:
        cat = classify_tag(tag)
        if cat:
            by_new_cat[cat].append((tag, count))
        else:
            unmapped_tags.append((tag, count))

    print("\n── Tags (5+ occurrences) grouped by NEW category ──")
    for cat in NEW_CATEGORIES:
        tags_in_cat = by_new_cat.get(cat, [])
        if tags_in_cat:
            total = sum(c for _, c in tags_in_cat)
            print(f"\n  [{cat}] ({len(tags_in_cat)} tags, {total:,} tag-occurrences)")
            for tag, count in sorted(tags_in_cat, key=lambda x: -x[1]):
                print(f"    {tag:40s} {count:>5,}")

    if unmapped_tags:
        print(f"\n  [UNMAPPED] ({len(unmapped_tags)} tags)")
        for tag, count in sorted(unmapped_tags, key=lambda x: -x[1]):
            print(f"    {tag:40s} {count:>5,}")

    # ─────────────────────────────────────────────────────────────────
    # PART C: Distribution estimate
    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("PART C: ESTIMATED EVENT DISTRIBUTION ACROSS 8 CATEGORIES")
    print("=" * 80)

    cat_event_count = Counter()

    # Kulturdaten: map via source_tags (use first matching tag)
    # For ambiguous tags, assign a provisional category
    PROVISIONAL_AMBIGUOUS = {
        "Recreation": "Community",
        "Festivals": "Arts & Culture",
        "Police": "Community",
        "Stages": "Arts & Culture",
        "Dance": "Nightlife",
        "Health": "Community",
    }

    FULL_KD_MAP = {**DEFINITE_MAP, **PROVISIONAL_AMBIGUOUS}

    for e in kd_events:
        stags = e.get("_clean_source_tags") or []
        mapped = False
        for t in stags:
            if t in FULL_KD_MAP:
                cat_event_count[FULL_KD_MAP[t]] += 1
                mapped = True
                break
        if not mapped:
            cat_event_count["(unmapped-kd)"] += 1

    # Non-kulturdaten: classify by tags, then fall back to category field
    CAT_FIELD_MAP = {
        "music": "Music",
        "nightlife": "Nightlife",
        "arts": "Arts & Culture",
        "arts_culture": "Arts & Culture",
        "arts & culture": "Arts & Culture",
        "food": "Food & Drink",
        "food_drink": "Food & Drink",
        "food & drink": "Food & Drink",
        "markets": "Markets",
        "market": "Markets",
        "community": "Community",
        "outdoors": "Outdoors",
        "outdoor": "Outdoors",
        "family": "Family",
        "concert": "Music",
        "club": "Nightlife",
        "party": "Nightlife",
        "exhibition": "Arts & Culture",
        "workshop": "Community",
        "talk": "Community",
        "sports": "Outdoors",
        "kids": "Family",
    }

    for src in non_kd_sources:
        for e in by_source.get(src, []):
            # Try tags first
            tags = e.get("tags") or []
            if isinstance(tags, str):
                tags = [tags]
            classified = None
            for t in tags:
                c = classify_tag(t.strip())
                if c:
                    classified = c
                    break
            # Fallback to category field
            if not classified:
                cat_raw = (e.get("category") or "").lower().strip()
                classified = CAT_FIELD_MAP.get(cat_raw)
            # Fallback: try source-level defaults
            if not classified:
                source_defaults = {
                    "jazzclubs": "Music",
                    "resident_advisor": "Music",
                    "planetarium": "Family",
                }
                classified = source_defaults.get(src)

            cat_event_count[classified or "(unmapped-other)"] += 1

    total_mapped = sum(cat_event_count[c] for c in NEW_CATEGORIES)
    total_all = sum(cat_event_count.values())

    print(f"\n{'Category':25s} {'Events':>8s} {'%':>6s}")
    print("-" * 42)
    for cat in NEW_CATEGORIES:
        n = cat_event_count[cat]
        pct = n / total_all * 100 if total_all else 0
        print(f"  {cat:23s} {n:>8,} {pct:>5.1f}%")
    print("-" * 42)
    print(f"  {'TOTAL MAPPED':23s} {total_mapped:>8,} {total_mapped/total_all*100 if total_all else 0:>5.1f}%")
    um_kd = cat_event_count.get("(unmapped-kd)", 0)
    um_other = cat_event_count.get("(unmapped-other)", 0)
    if um_kd or um_other:
        print(f"  {'unmapped (kulturdaten)':23s} {um_kd:>8,}")
        print(f"  {'unmapped (other)':23s} {um_other:>8,}")
    print(f"  {'GRAND TOTAL':23s} {total_all:>8,}")

    # ─────────────────────────────────────────────────────────────────
    # PART D: Subcategory proposals
    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("PART D: PROPOSED SUBCATEGORIES PER CATEGORY")
    print("=" * 80)

    # Define subcategory clusters based on keyword groups
    SUBCATEGORY_CLUSTERS = {
        "Music": {
            "Live Concerts": ["concert", "live music", "live", "band", "singer", "songwriter", "acoustic", "choir", "vocal", "orchestra"],
            "Electronic & DJ": ["electronic", "techno", "house", "dj", "rave", "ambient", "synth", "bass", "drum and bass", "minimal", "trance"],
            "Jazz & Blues": ["jazz", "blues", "swing", "bossa nova", "improvisation"],
            "Classical & Opera": ["classical", "opera", "piano", "chamber", "symphony", "philharmonic"],
            "World & Latin": ["latin", "salsa", "cumbia", "afrobeat", "reggae", "world music", "african", "caribbean"],
            "Hip Hop, R&B & Pop": ["hip hop", "hip-hop", "rap", "r&b", "rnb", "pop", "indie", "rock", "punk", "metal", "funk", "soul"],
        },
        "Nightlife": {
            "Club Nights": ["club", "clubbing", "nightclub", "dancefloor", "dance floor", "door", "berghain", "tresor", "watergate"],
            "Parties & Raves": ["party", "rave", "afterparty", "after-party", "dance party"],
            "Bars & Cocktails": ["bar", "cocktail", "drinks", "pub", "karaoke", "pub crawl"],
            "Queer & Alternative": ["queer party", "drag", "lgbtq", "fetish", "kink", "burlesque", "queer"],
        },
        "Arts & Culture": {
            "Exhibitions & Galleries": ["exhibition", "gallery", "museum", "visual art", "contemporary art", "modern art"],
            "Theatre & Performance": ["theater", "theatre", "performance", "dance performance", "ballet", "stage"],
            "Film & Cinema": ["film", "cinema", "movie", "screening", "documentary"],
            "Literature & Readings": ["literature", "poetry", "reading", "book", "author"],
            "Comedy & Improv": ["comedy", "stand-up", "standup", "improv", "open mic"],
            "Photography & Design": ["photography", "design", "architecture", "illustration", "digital art", "street art"],
        },
        "Food & Drink": {
            "Dining Experiences": ["dinner", "supper club", "restaurant", "dining", "brunch", "lunch", "tasting"],
            "Cooking & Workshops": ["cooking", "culinary", "baking", "class"],
            "Wine, Beer & Spirits": ["wine", "beer", "brewery", "spirits", "tasting"],
            "Street Food & Pop-ups": ["street food", "food market", "pop-up", "food truck"],
        },
        "Markets": {
            "Flea & Vintage Markets": ["flea market", "vintage", "antique", "second-hand"],
            "Craft & Makers Markets": ["craft market", "handmade", "makers", "artisan"],
            "Weekly & Farmers Markets": ["weekly market", "farmers market", "wochenmarkt"],
            "Seasonal & Holiday Markets": ["christmas market", "weihnachtsmarkt", "easter", "seasonal"],
        },
        "Community": {
            "Workshops & Learning": ["workshop", "class", "course", "training", "education", "seminar"],
            "Tech & Startups": ["tech", "startup", "coding", "programming", "hackathon", "ai", "data"],
            "Talks & Panels": ["talk", "discussion", "panel", "lecture", "conference"],
            "Meetups & Networking": ["meetup", "networking", "social", "coworking", "entrepreneur", "business"],
            "Wellness & Mindfulness": ["meditation", "yoga", "wellness", "mindfulness", "spiritual", "health"],
            "Activism & Social": ["activism", "protest", "political", "fundraiser", "charity", "volunteering"],
        },
        "Outdoors": {
            "Walking & Hiking": ["walk", "walking tour", "hike", "hiking", "nature"],
            "Cycling & Running": ["bike", "cycling", "running", "marathon"],
            "Parks & Gardens": ["park", "garden", "picnic", "bbq", "outdoor cinema"],
            "Water Activities": ["swim", "lake", "river", "boat", "kayak"],
            "Sports & Fitness": ["sports", "fitness", "basketball", "football", "volleyball", "climbing"],
        },
        "Family": {
            "Kids Activities": ["kids", "children", "child", "toddler", "baby", "kid-friendly", "family-friendly"],
            "Theatre & Shows": ["puppet", "circus", "magic show", "children's theatre"],
            "Science & Discovery": ["planetarium", "science", "experiment", "nature"],
            "Creative Workshops": ["painting", "crafts", "building", "music class"],
        },
    }

    # Count how many events would fall into each subcategory
    # For non-kd events, check tags against subcategory keywords
    for cat in NEW_CATEGORIES:
        subcats = SUBCATEGORY_CLUSTERS.get(cat, {})
        if not subcats:
            continue

        print(f"\n{'─' * 60}")
        print(f"  {cat}")
        print(f"{'─' * 60}")

        subcat_counts = Counter()
        subcat_tags_found = defaultdict(Counter)

        # Check non-kd tags
        for tag, count in tag_counter.items():
            t_lower = tag.lower()
            for subcat, keywords in subcats.items():
                for kw in keywords:
                    if kw in t_lower or t_lower in kw:
                        subcat_counts[subcat] += count
                        subcat_tags_found[subcat][tag] += count
                        break

        # Check kulturdaten source_tags
        kd_subcat_map = {
            "Music": {"Live Concerts": ["Music"], "Electronic & DJ": [], "Jazz & Blues": []},
            "Nightlife": {"Club Nights": ["Dance"], "Parties & Raves": []},
            "Arts & Culture": {
                "Exhibitions & Galleries": ["Exhibitions", "Art"],
                "Theatre & Performance": ["Stages"],
                "Film & Cinema": [],
                "Comedy & Improv": [],
            },
            "Markets": {
                "Weekly & Farmers Markets": ["WeeklyMarkets"],
                "Seasonal & Holiday Markets": ["ChristmasTime"],
            },
            "Community": {
                "Workshops & Learning": ["Education"],
                "Talks & Panels": ["Lectures", "Conferences", "InformationEvents"],
                "Activism & Social": ["Politics", "Women"],
                "Meetups & Networking": ["Seniors"],
                "Wellness & Mindfulness": ["Health"],
            },
            "Outdoors": {
                "Walking & Hiking": ["Walks"],
            },
            "Family": {
                "Kids Activities": ["Children"],
            },
        }

        cat_kd_map = kd_subcat_map.get(cat, {})
        for subcat, kd_tags in cat_kd_map.items():
            for kd_tag in kd_tags:
                n = kd_tag_counter.get(kd_tag, 0)
                if n:
                    subcat_counts[subcat] += n
                    subcat_tags_found[subcat][f"kd:{kd_tag}"] += n

        for subcat in subcats:
            count = subcat_counts.get(subcat, 0)
            top_tags = subcat_tags_found.get(subcat, Counter()).most_common(8)
            tag_str = ", ".join(f"{t}({c})" for t, c in top_tags)
            print(f"\n    {subcat:30s}  ~{count:>5,} events")
            if tag_str:
                print(f"      Tags: {tag_str}")

    print("\n" + "=" * 80)
    print("END OF TAXONOMY ANALYSIS")
    print("=" * 80)


if __name__ == "__main__":
    main()
