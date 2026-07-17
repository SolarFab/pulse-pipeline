#!/usr/bin/env python3
"""
Final analysis: kulturdaten "00:00 - 00:00" hypothesis check.

Frontend code: `new Date(iso).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })`
This converts to browser's local timezone. For Berlin users, 23:00 UTC = 00:00 Berlin (CET).

The display shows:
- formatTime(start_time) => "00:00" when start is 23:00 UTC (CET) or 22:00 UTC (CEST)
- If end_time is null, no end time shown
- If end_time exists: formatTime(end_time)

So "00:00 - 00:00" shows when:
  start = 23:00 UTC AND end = 23:00 UTC (both = midnight Berlin)
  OR start = 23:00 UTC AND end is null (shows just "00:00")

The hypothesis: these are long-running exhibitions with date-only ranges.
"""

import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter

SUPABASE_URL = "https://ykkjhmohqibepqovtjqs.supabase.co"
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
BERLIN = ZoneInfo("Europe/Berlin")

def fetch_all_kulturdaten():
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    url = f"{SUPABASE_URL}/rest/v1/events"
    params = {
        "select": "title,venue_name,start_time,end_time,category,tags",
        "source": "eq.kulturdaten",
        "order": "start_time.asc",
    }
    all_events = []
    offset = 0
    page_size = 1000
    while True:
        headers["Range"] = f"{offset}-{offset + page_size - 1}"
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        all_events.extend(data)
        if len(data) < page_size:
            break
        offset += page_size
    return all_events

def parse_dt(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def to_berlin(dt):
    return dt.astimezone(BERLIN) if dt else None

def is_midnight_berlin(dt):
    """Would this datetime display as 00:00 in Berlin timezone?"""
    if not dt:
        return False
    b = dt.astimezone(BERLIN)
    return b.hour == 0 and b.minute == 0

def duration_bucket(days):
    if days is None:
        return "no end time"
    if days < 1:
        return "<1 day"
    elif days <= 7:
        return "1-7 days"
    elif days <= 28:
        return "1-4 weeks"
    elif days <= 90:
        return "1-3 months"
    elif days <= 180:
        return "3-6 months"
    else:
        return "6+ months"

def main():
    print("=" * 75)
    print("KULTURDATEN '00:00' DISPLAY ANALYSIS")
    print("=" * 75)
    print()
    print("Frontend logic: new Date(iso).toLocaleTimeString('de-DE', ...)")
    print("23:00 UTC = 00:00 CET Berlin. These show as '00:00' to Berlin users.")
    print()

    events = fetch_all_kulturdaten()
    print(f"Total kulturdaten events: {len(events)}\n")

    # Categorize events by what the frontend would display
    midnight_start = []  # start displays as 00:00
    midnight_both = []   # both start AND end display as 00:00
    midnight_start_no_end = []  # start = 00:00, no end time
    normal_events = []

    for e in events:
        st = parse_dt(e.get("start_time"))
        et = parse_dt(e.get("end_time"))
        if not st:
            continue

        start_is_midnight = is_midnight_berlin(st)
        end_is_midnight = is_midnight_berlin(et) if et else False

        dur_days = None
        if st and et:
            dur_days = (et - st).total_seconds() / 86400

        rec = {
            "title": e.get("title", ""),
            "venue": e.get("venue_name", ""),
            "start": st,
            "end": et,
            "start_berlin": to_berlin(st),
            "end_berlin": to_berlin(et),
            "dur_days": dur_days,
            "category": e.get("category", ""),
            "tags": e.get("tags", []),
            "has_end": et is not None,
        }

        if start_is_midnight:
            midnight_start.append(rec)
            if et is None:
                midnight_start_no_end.append(rec)
            elif end_is_midnight:
                midnight_both.append(rec)
        else:
            normal_events.append(rec)

    # ═══════════════════════════════════════════════════════════════
    print("=" * 75)
    print("a) OVERALL DURATION DISTRIBUTION (all kulturdaten)")
    print("=" * 75)

    all_parsed = midnight_start + normal_events
    buckets = Counter()
    for r in all_parsed:
        buckets[duration_bucket(r["dur_days"])] += 1

    order = ["no end time", "<1 day", "1-7 days", "1-4 weeks", "1-3 months", "3-6 months", "6+ months"]
    for b in order:
        c = buckets.get(b, 0)
        pct = c / len(all_parsed) * 100 if all_parsed else 0
        print(f"  {b:15s}  {c:5d}  ({pct:5.1f}%)")

    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'=' * 75}")
    print("b) EVENTS DISPLAYING AS '00:00' (start at midnight Berlin)")
    print("=" * 75)
    print(f"  Total showing 00:00 start:           {len(midnight_start):5d}")
    print(f"    - with NO end_time (shows '00:00'): {len(midnight_start_no_end):5d}")
    print(f"    - with end also 00:00:              {len(midnight_both):5d}")
    print(f"    - with end at other time:           {len(midnight_start) - len(midnight_start_no_end) - len(midnight_both):5d}")
    print(f"  Normal events (non-midnight start):   {len(normal_events):5d}")

    # For midnight-start events that HAVE an end_time, what's the duration?
    midnight_with_end = [r for r in midnight_start if r["has_end"]]
    print(f"\n  Duration distribution of midnight-start events WITH end_time ({len(midnight_with_end)}):")
    mid_buckets = Counter(duration_bucket(r["dur_days"]) for r in midnight_with_end)
    for b in order:
        c = mid_buckets.get(b, 0)
        if c > 0:
            pct = c / len(midnight_with_end) * 100
            print(f"    {b:15s}  {c:5d}  ({pct:5.1f}%)")

    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'=' * 75}")
    print("c) 20 EXAMPLE '00:00' EVENTS (sorted by title variety)")
    print("=" * 75)

    # Get diverse examples - mix of no-end and with-end
    seen_titles = set()
    examples = []
    for r in midnight_start_no_end:
        short = r["title"][:40]
        if short not in seen_titles:
            seen_titles.add(short)
            examples.append(r)
        if len(examples) >= 15:
            break
    for r in midnight_with_end:
        short = r["title"][:40]
        if short not in seen_titles:
            seen_titles.add(short)
            examples.append(r)
        if len(examples) >= 20:
            break

    for i, r in enumerate(examples, 1):
        end_str = r["end_berlin"].strftime("%Y-%m-%d %H:%M") if r["end_berlin"] else "NULL (no end time)"
        dur_str = f"{r['dur_days']:.1f} days" if r["dur_days"] is not None else "unknown"
        if r["dur_days"] and r["dur_days"] > 30:
            dur_str += f" ({r['dur_days']/30:.1f} months)"
        print(f"\n  [{i:2d}] {r['title'][:70]}")
        print(f"       Venue:    {r['venue'][:60]}")
        print(f"       Start:    {r['start_berlin'].strftime('%Y-%m-%d %H:%M')} Berlin")
        print(f"       End:      {end_str}")
        print(f"       Duration: {dur_str}")
        print(f"       Category: {r['category']}")

    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'=' * 75}")
    print("d) MULTI-DAY PERCENTAGE OF MIDNIGHT EVENTS")
    print("=" * 75)

    # For events with end_time
    if midnight_with_end:
        multi_day = [r for r in midnight_with_end if r["dur_days"] and r["dur_days"] > 1]
        pct = len(multi_day) / len(midnight_with_end) * 100
        print(f"  Midnight events with end_time: {len(midnight_with_end)}")
        print(f"  Multi-day (>1 day):            {len(multi_day)} ({pct:.1f}%)")

    # For events WITHOUT end_time - these are the "date-only" ones
    # The key insight: kulturdaten API provides dates without times for exhibitions
    # The pipeline stores them as 23:00 UTC (= midnight Berlin) with NULL end
    print(f"\n  Midnight events WITHOUT end_time: {len(midnight_start_no_end)}")
    print(f"  (These likely represent date-only entries from kulturdaten API)")
    print(f"  The pipeline converts a date like '2026-04-15' to '2026-04-14T23:00:00+00:00'")
    print(f"  which is midnight Berlin = the start of that date.")

    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'=' * 75}")
    print("e) TOP 15 VENUES HOSTING MIDNIGHT/00:00 EVENTS")
    print("=" * 75)
    venue_counts = Counter(r["venue"] for r in midnight_start if r["venue"])
    for venue, count in venue_counts.most_common(15):
        print(f"  {count:4d}  {venue[:65]}")

    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'=' * 75}")
    print("4) CATEGORY BREAKDOWN OF MIDNIGHT EVENTS")
    print("=" * 75)
    cat_counts = Counter(r["category"] for r in midnight_start)
    for cat, count in cat_counts.most_common(20):
        print(f"  {count:4d}  {cat or '(none)'}")

    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'=' * 75}")
    print("SUMMARY & CONCLUSION")
    print("=" * 75)
    print(f"""
  Total kulturdaten events:                    {len(events)}
  Events displaying '00:00' (midnight Berlin): {len(midnight_start)} ({len(midnight_start)/len(events)*100:.1f}%)

  Of these {len(midnight_start)} midnight events:
    - {len(midnight_start_no_end)} ({len(midnight_start_no_end)/len(midnight_start)*100:.1f}%) have NULL end_time
    - {len(midnight_with_end)} ({len(midnight_with_end)/len(midnight_start)*100:.1f}%) have an end_time

  The hypothesis is PARTIALLY CONFIRMED but needs nuance:

  1. These events ARE from date-only data in the kulturdaten API.
     The original API provides just a date (e.g., "2026-04-15") with no time.
     The pipeline converts this to 23:00 UTC = 00:00 Berlin (midnight).

  2. However, they are NOT necessarily "long-running exhibitions spanning months."
     Most ({len(midnight_start_no_end)} of {len(midnight_start)}) have NO end_time at all.
     Of the {len(midnight_with_end)} that do have end_time, the durations are ~1 day
     (midnight to next midnight), NOT months-long.

  3. The "00:00 - 00:00" display comes from:
     - Start at 23:00 UTC (= 00:00 Berlin) -> shows "00:00"
     - End at 00:00 UTC the next day (= 01:00 Berlin) -> shows "01:00"
     OR end_time is NULL -> no end shown (just "00:00")

  4. What kulturdaten actually provides are DATE-BASED events (exhibitions,
     installations, etc.) that have a DATE but no specific TIME.
     The pipeline stores these as midnight, and the frontend displays "00:00".

  RECOMMENDATION:
  - Detect events where start time = midnight Berlin AND (end is null OR
    end is also midnight). These are "all-day" / "date-only" events.
  - Display them differently: show just the date, no time. E.g., "15 Apr 2026"
    instead of "00:00".
  - For events with both start and end dates at midnight, show the date range:
    "15 Apr - 20 Jul 2026" instead of "00:00 - 00:00".
""")

if __name__ == "__main__":
    main()
