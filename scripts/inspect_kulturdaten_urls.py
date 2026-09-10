import os
#!/usr/bin/env python3
"""Inspect kulturdaten API for website/URL fields and check Supabase source_url coverage."""

import json
import requests
from urllib.parse import urlparse
from collections import Counter

# ── Supabase config ──
SUPABASE_URL = "https://ykkjhmohqibepqovtjqs.supabase.co"
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
HEADERS_SB = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}

KULTUR_BASE = "https://api-v2.kulturdaten.berlin/api"

def pp(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))

# ═══════════════════════════════════════════════
# PART 1: Fetch specific location & attraction
# ═══════════════════════════════════════════════
print("=" * 70)
print("PART 1a: GET /api/locations/L_2JMAJPC5JCQL (Haus am Waldsee)")
print("=" * 70)
r = requests.get(f"{KULTUR_BASE}/locations/L_2JMAJPC5JCQL")
if r.ok:
    data = r.json()
    pp(data)
else:
    print(f"  HTTP {r.status_code}: {r.text[:500]}")

print()
print("=" * 70)
print("PART 1b: GET /api/attractions/A_MKRR52ZMWPS5 (Gianna Surangkanjanajai)")
print("=" * 70)
r = requests.get(f"{KULTUR_BASE}/attractions/A_MKRR52ZMWPS5")
if r.ok:
    data = r.json()
    pp(data)
else:
    print(f"  HTTP {r.status_code}: {r.text[:500]}")

# ═══════════════════════════════════════════════
# PART 2: Fetch 10 random locations, check website field
# ═══════════════════════════════════════════════
print()
print("=" * 70)
print("PART 2: Fetch 10 locations and check for website/url fields")
print("=" * 70)
r = requests.get(f"{KULTUR_BASE}/locations", params={"page": 1, "size": 10})
if r.ok:
    data = r.json()
    locations = data.get("data", data.get("content", data)) if isinstance(data, dict) else data
    if isinstance(locations, dict):
        # might be paginated
        for k in locations:
            if isinstance(locations[k], list):
                locations = locations[k]
                break
    if isinstance(locations, list):
        for loc in locations:
            loc_id = loc.get("identifier", loc.get("id", "?"))
            # Find title
            title_obj = loc.get("title", {})
            if isinstance(title_obj, dict):
                title = title_obj.get("de", title_obj.get("en", str(title_obj)))
            else:
                title = str(title_obj)
            # Find website
            website = loc.get("website", loc.get("url", loc.get("homepage", None)))
            ext_links = loc.get("externalLinks", loc.get("external_links", None))
            print(f"  {loc_id}: {title[:50]:50s} website={website}  externalLinks={ext_links}")
    else:
        print("  Unexpected response structure:")
        pp(data)
else:
    print(f"  HTTP {r.status_code}: {r.text[:500]}")

# Also try listing with different param names
print("\n  --- Full keys of first location for reference ---")
r2 = requests.get(f"{KULTUR_BASE}/locations", params={"page": 1, "size": 1})
if r2.ok:
    d = r2.json()
    # Print top-level keys and first item keys
    print(f"  Top-level keys: {list(d.keys()) if isinstance(d, dict) else 'list'}")
    items = None
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(v, list) and len(v) > 0:
                items = v
                break
    if items and len(items) > 0:
        print(f"  First location keys: {list(items[0].keys())}")

# ═══════════════════════════════════════════════
# PART 3: Supabase source_url analysis
# ═══════════════════════════════════════════════
print()
print("=" * 70)
print("PART 3: Supabase events — source_url analysis")
print("=" * 70)

# Count events with source_url set (kulturdaten only)
r = requests.get(
    f"{SUPABASE_URL}/rest/v1/events",
    headers={**HEADERS_SB, "Prefer": "count=exact"},
    params={
        "select": "id",
        "source": "eq.kulturdaten",
        "source_url": "not.is.null",
        "limit": 0,
    },
)
has_url_count = int(r.headers.get("content-range", "*/0").split("/")[-1]) if r.ok else "error"

r = requests.get(
    f"{SUPABASE_URL}/rest/v1/events",
    headers={**HEADERS_SB, "Prefer": "count=exact"},
    params={
        "select": "id",
        "source": "eq.kulturdaten",
        "source_url": "is.null",
        "limit": 0,
    },
)
no_url_count = int(r.headers.get("content-range", "*/0").split("/")[-1]) if r.ok else "error"

# Also count where source_url is empty string
r = requests.get(
    f"{SUPABASE_URL}/rest/v1/events",
    headers={**HEADERS_SB, "Prefer": "count=exact"},
    params={
        "select": "id",
        "source": "eq.kulturdaten",
        "source_url": "eq.",
        "limit": 0,
    },
)
empty_url_count = int(r.headers.get("content-range", "*/0").split("/")[-1]) if r.ok else "error"

print(f"  kulturdaten events with source_url set:   {has_url_count}")
print(f"  kulturdaten events with source_url NULL:   {no_url_count}")
print(f"  kulturdaten events with source_url empty:  {empty_url_count}")

# Total kulturdaten events
r = requests.get(
    f"{SUPABASE_URL}/rest/v1/events",
    headers={**HEADERS_SB, "Prefer": "count=exact"},
    params={
        "select": "id",
        "source": "eq.kulturdaten",
        "limit": 0,
    },
)
total_kultur = int(r.headers.get("content-range", "*/0").split("/")[-1]) if r.ok else "error"
print(f"  kulturdaten events TOTAL:                  {total_kultur}")

# All sources
r = requests.get(
    f"{SUPABASE_URL}/rest/v1/events",
    headers={**HEADERS_SB, "Prefer": "count=exact"},
    params={"select": "id", "limit": 0},
)
total_all = int(r.headers.get("content-range", "*/0").split("/")[-1]) if r.ok else "error"
print(f"  ALL events total:                          {total_all}")

# Top 20 source_url domains — fetch source_urls in batches
print(f"\n  --- Top 20 source_url domains (all sources) ---")
domain_counter = Counter()
offset = 0
batch = 1000
while True:
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/events",
        headers=HEADERS_SB,
        params={
            "select": "source_url",
            "source_url": "not.is.null",
            "limit": batch,
            "offset": offset,
        },
    )
    if not r.ok:
        print(f"  Error fetching: {r.status_code}")
        break
    rows = r.json()
    if not rows:
        break
    for row in rows:
        url = row.get("source_url", "")
        if url:
            try:
                domain = urlparse(url).netloc
                domain_counter[domain] += 1
            except Exception:
                domain_counter["<parse-error>"] += 1
    offset += batch
    if len(rows) < batch:
        break

for domain, count in domain_counter.most_common(20):
    print(f"    {count:5d}  {domain}")

# Events without source_url that have a venue_id (could look up venue website)
print(f"\n  --- Events without source_url but with venue_id ---")
r = requests.get(
    f"{SUPABASE_URL}/rest/v1/events",
    headers={**HEADERS_SB, "Prefer": "count=exact"},
    params={
        "select": "id",
        "source": "eq.kulturdaten",
        "source_url": "is.null",
        "venue_id": "not.is.null",
        "limit": 0,
    },
)
with_venue = int(r.headers.get("content-range", "*/0").split("/")[-1]) if r.ok else "error"
print(f"  kulturdaten events with NULL source_url AND venue_id set: {with_venue}")

# How many venues have a website_url?
r = requests.get(
    f"{SUPABASE_URL}/rest/v1/venues",
    headers={**HEADERS_SB, "Prefer": "count=exact"},
    params={"select": "id", "website_url": "not.is.null", "limit": 0},
)
venues_with_web = int(r.headers.get("content-range", "*/0").split("/")[-1]) if r.ok else "error"

r = requests.get(
    f"{SUPABASE_URL}/rest/v1/venues",
    headers={**HEADERS_SB, "Prefer": "count=exact"},
    params={"select": "id", "limit": 0},
)
venues_total = int(r.headers.get("content-range", "*/0").split("/")[-1]) if r.ok else "error"
print(f"  Venues with website_url: {venues_with_web} / {venues_total}")

# Check a few venue website_urls
print(f"\n  --- Sample venue website_urls ---")
r = requests.get(
    f"{SUPABASE_URL}/rest/v1/venues",
    headers=HEADERS_SB,
    params={"select": "name,website_url", "website_url": "not.is.null", "limit": 10},
)
if r.ok:
    for v in r.json():
        print(f"    {v['name'][:40]:40s}  {v.get('website_url', '')}")

print("\nDone.")
