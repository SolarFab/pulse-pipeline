#!/usr/bin/env python3
"""One-off: replace Eventbrite teaser summaries with full descriptions (workshop F5).

The scraper stored the listing `summary` (~140 chars); the full description lives in
the event page's JSON-LD. Thin text degraded categorization, neighborhood signals and
embeddings ("Meanwhile in Berlin" case). This fetches the page, extracts the schema.org
Event description, and clears embedding/embed_hash so the next backfill re-embeds with
the rich text.
"""

from __future__ import annotations

import html as ihtml
import json
import re
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

from db.supabase import get_client  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (compatible; PulseBerlin/1.0)"}
LDJSON = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.DOTALL)
TAGS = re.compile(r"<[^>]+>")


def _clean(html_text: str) -> str:
    return re.sub(r"\s+", " ", ihtml.unescape(TAGS.sub(" ", html_text))).strip()


def full_description(url: str) -> str | None:
    try:
        r = httpx.get(url, headers=UA, timeout=20, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError:
        return None

    # Primary source: the page's embedded structuredContent (full HTML description).
    # Eventbrite's JSON-LD only mirrors the ~140-char teaser, so it's the fallback.
    idx = r.text.find('"structuredContent":')
    if idx != -1:
        start = r.text.find("{", idx)
        try:
            blob, _ = json.JSONDecoder().raw_decode(r.text[start:])
            parts = [m.get("text", "") for m in blob.get("modules", [])
                     if isinstance(m, dict) and m.get("type") == "text"]
            desc = _clean(" ".join(parts))
            if desc:
                return desc[:1500]
        except (json.JSONDecodeError, AttributeError):
            pass

    for block in LDJSON.findall(r.text):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and str(item.get("@type", "")).endswith("Event"):
                desc = _clean(item.get("description") or "")
                if desc:
                    return desc[:1500]
    return None


def main() -> None:
    client = get_client()
    rows = (client.table("events")
            .select("id,title,description,source_url")
            .eq("source", "eventbrite").eq("is_active", True)
            .gte("start_time", "now()").execute().data) or []
    thin = [r for r in rows if len(r.get("description") or "") < 300 and r.get("source_url")]
    print(f"{len(rows)} upcoming eventbrite events; {len(thin)} with thin descriptions")
    enriched = failed = 0
    for r in thin:
        time.sleep(0.4)
        desc = full_description(r["source_url"])
        if desc and len(desc) > len(r.get("description") or ""):
            client.table("events").update({
                "description": desc,
                "embedding": None, "embed_hash": None,  # force re-embed with rich text
            }).eq("id", r["id"]).execute()
            enriched += 1
        else:
            failed += 1
        if (enriched + failed) % 25 == 0:
            print(f"  {enriched + failed}/{len(thin)} (enriched {enriched})", flush=True)
    print(f"Done: enriched {enriched}, no improvement {failed}")


if __name__ == "__main__":
    main()
