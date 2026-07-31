#!/usr/bin/env python3
"""Seed the canonical `taxonomy` table (unify-taxonomy §1.2). Idempotent upsert.

Staging logic (design §3: live app correct at every step):
- current categories (incl. `family`, `outdoors`) seeded ACTIVE — chips keep working;
- `sports-wellness` seeded INACTIVE until the §4 re-filing flips it on and
  deactivates `family` + `outdoors`.

Usage:
    python scripts/seed_taxonomy.py --dry-run   # print the plan
    python scripts/seed_taxonomy.py             # write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

from db.supabase import get_client  # noqa: E402
from pipeline.taxonomy import SUBCATEGORY_KEYWORDS  # noqa: E402

# (label_de, label_en) — display names; slugs stay English and stable.
CATEGORY_LABELS: dict[str, tuple[str, str]] = {
    "music": ("Musik", "Music"),
    "nightlife": ("Nachtleben", "Nightlife"),
    "culture": ("Kultur", "Culture"),
    "food": ("Essen & Trinken", "Food & Drink"),
    "markets": ("Märkte", "Markets"),
    "workshops": ("Workshops", "Workshops"),
    "meetups": ("Meetups", "Meetups"),
    "outdoors": ("Draußen", "Outdoors"),                 # legacy — deactivated in §4
    "family": ("Familie", "Family"),                     # legacy — deactivated in §4
    "sports-wellness": ("Sport & Wellness", "Sports & Wellness"),  # successor, inactive until §4
}

SUBCATEGORY_LABELS: dict[str, tuple[str, str]] = {
    "classical": ("Klassik", "Classical"), "electronic": ("Elektronisch", "Electronic"),
    "hip-hop": ("Hip-Hop", "Hip-Hop"), "jazz-blues": ("Jazz & Blues", "Jazz & Blues"),
    "latin": ("Latin", "Latin"), "live-concert": ("Livekonzert", "Live Concert"),
    "rock-pop": ("Rock & Pop", "Rock & Pop"), "world-folk": ("World & Folk", "World & Folk"),
    "bar-event": ("Bar-Event", "Bar Event"), "club-night": ("Clubnacht", "Club Night"),
    "comedy": ("Comedy", "Comedy"), "karaoke": ("Karaoke", "Karaoke"), "party": ("Party", "Party"),
    "cinema": ("Kino", "Cinema"), "exhibition": ("Ausstellung", "Exhibition"),
    "festival": ("Festival", "Festival"), "gallery": ("Galerie", "Gallery"),
    "reading": ("Lesung", "Reading"), "theater": ("Theater", "Theater"),
    "brunch": ("Brunch", "Brunch"), "dining-event": ("Dinner-Event", "Dining Event"),
    "food-market": ("Foodmarkt", "Food Market"), "pop-up": ("Pop-up", "Pop-up"),
    "tasting": ("Verkostung", "Tasting"), "weekly-market": ("Wochenmarkt", "Weekly Market"),
    "craft-market": ("Handwerksmarkt", "Craft Market"),
    "design-market": ("Designmarkt", "Design Market"), "flea-market": ("Flohmarkt", "Flea Market"),
    "pop-up-fashion": ("Pop-up Fashion", "Pop-up Fashion"),
    "secondhand": ("Secondhand", "Secondhand"),
    "craft": ("Handwerk", "Craft"), "creative-workshop": ("Kreativworkshop", "Creative Workshop"),
    "dance-class": ("Tanzkurs", "Dance Class"), "digital-skills": ("Digital Skills", "Digital Skills"),
    "language": ("Sprachen", "Language"),
    "activism": ("Aktivismus", "Activism"), "community": ("Community", "Community"),
    "networking": ("Networking", "Networking"), "talk-panel": ("Talk & Panel", "Talk & Panel"),
    "tech-startup": ("Tech & Startup", "Tech & Startup"),
    "bike-tour": ("Radtour", "Bike Tour"), "outdoor-cinema": ("Open-Air-Kino", "Outdoor Cinema"),
    "sports": ("Sport", "Sports"), "walking-tour": ("Stadtführung", "Walking Tour"),
    "yoga-fitness": ("Yoga & Fitness", "Yoga & Fitness"),
    "family-event": ("Familien-Event", "Family Event"), "kids-program": ("Kinderprogramm", "Kids Program"),
    "museum-for-kids": ("Museum für Kinder", "Museum for Kids"),
    "playground": ("Spielplatz", "Playground"),
}

INACTIVE_CATEGORIES = {"sports-wellness"}  # flipped active in §4
# §4 moves sports-ish subcategories here; until then it has none of its own.
EXTRA_CATEGORIES = {"sports-wellness": []}


def build_rows() -> list[dict]:
    rows = []
    cats = {**{c: sorted(s) for c, s in SUBCATEGORY_KEYWORDS.items()}, **EXTRA_CATEGORIES}
    for order, (cat, subs) in enumerate(cats.items()):
        de, en = CATEGORY_LABELS[cat]
        rows.append({
            "category_slug": cat, "subcategory_slug": None, "label_de": de, "label_en": en,
            "sort_order": order * 100, "is_active": cat not in INACTIVE_CATEGORIES,
        })
        for i, sub in enumerate(subs):
            sde, sen = SUBCATEGORY_LABELS[sub]
            rows.append({
                "category_slug": cat, "subcategory_slug": sub, "label_de": sde, "label_en": sen,
                "sort_order": order * 100 + i + 1, "is_active": cat not in INACTIVE_CATEGORIES,
            })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = build_rows()
    print(f"{len(rows)} taxonomy rows "
          f"({sum(1 for r in rows if r['subcategory_slug'] is None)} categories)")
    if args.dry_run:
        for r in rows:
            flag = "" if r["is_active"] else "  [inactive]"
            print(f"  {r['category_slug']:16} {r['subcategory_slug'] or '—':20} "
                  f"{r['label_de']} / {r['label_en']}{flag}")
        return

    client = get_client()
    client.table("taxonomy").upsert(rows, on_conflict="category_slug,subcategory_slug").execute()
    print("Seeded.")


if __name__ == "__main__":
    main()
