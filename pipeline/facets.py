"""Facet detection (unify-taxonomy §2.2): cross-cutting boolean properties of events.

Keyword-based, DE+EN, deliberately conservative: no signal → False (a facet toggle
showing too little is fine; a wrong category-style guess is not). No LLM on this path.

Wired into the scrape pass in scrapers/base.py; columns added by
db/migrations/002_event_facets.sql (applied).
"""

from __future__ import annotations

import re

_FAMILY = re.compile(
    # \w* endings: German compounds (Kinderprogramm, familienfreundlich, Kleinkinder…)
    r"\b(kinder\w*|familien?\w*|family|kids?|kleinkind\w*|jugendliche\w*|"
    r"ab\s?\d{1,2}\s?jahren?|children|toddler|puppentheater|kasperle\w*)\b",
    re.IGNORECASE,
)
# Signals that override a family match (adult-only contexts)
_FAMILY_VETO = re.compile(r"\b(ab\s?18|18\+|adults?\s?only|fsk\s?18)\b", re.IGNORECASE)

_OUTDOOR = re.compile(
    r"\b(open[\s-]?air|drau[ßs]en|outdoor|unter freiem himmel|im park|"
    r"im garten|biergarten|am ufer|strandbar|freiluft|rooftop|dachterrasse)\b",
    re.IGNORECASE,
)

_FREE = re.compile(
    r"\b(eintritt\s?frei|freier eintritt|kostenlos|kostenfrei|gratis|"
    r"free\s?(entry|entrance|admission)|umsonst|spendenbasis|pay what you (want|can))\b",
    re.IGNORECASE,
)


def detect_facets(event: dict) -> dict[str, bool]:
    """Return the three facet booleans for an event dict (title/description/price/venue_name)."""
    text = " ".join(
        str(event.get(f) or "") for f in ("title", "description", "venue_name", "price")
    )
    family = bool(_FAMILY.search(text)) and not _FAMILY_VETO.search(text)
    outdoor = bool(_OUTDOOR.search(text))
    free = bool(_FREE.search(text)) or event.get("price_cents") == 0
    return {"family_friendly": family, "outdoor": outdoor, "free_entry": free}
