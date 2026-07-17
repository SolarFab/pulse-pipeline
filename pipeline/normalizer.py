"""
Normalizer: converts raw scraped data into the unified Event schema
that maps directly to the Supabase events table.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from dateutil import parser as dateparser
from pydantic import BaseModel, field_validator, model_validator

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {
    "music", "nightlife", "food", "culture", "markets",
    "workshops", "meetups", "outdoors", "family",
}

BERLIN_TZ = ZoneInfo("Europe/Berlin")


class RawEvent(BaseModel):
    """Loose input model — everything optional except title, venue, start_time, source."""
    title: str
    venue_name: str
    source: str

    start_time: Any  # str | datetime — normalised below
    end_time: Any = None

    lat: float | None = None
    lng: float | None = None
    neighborhood: str | None = None
    address: str | None = None

    category: str | None = None
    subcategory: str | None = None
    tags: list[str] | None = None

    description: str | None = None
    price: str | None = None
    price_cents: int | None = None
    image_url: str | None = None

    source_url: str | None = None
    source_id: str | None = None

    # Community submissions only
    submitted_by: str | None = None
    submission_link: str | None = None
    status: str = "active"

    source_tags: list[str] | None = None
    quality_score: float | None = None

    @field_validator("title", "venue_name", mode="before")
    @classmethod
    def strip_text(cls, v: Any) -> str:
        return str(v).strip()

    @field_validator("category", mode="before")
    @classmethod
    def normalise_category(cls, v: Any) -> str | None:
        if v is None:
            return None
        cat = str(v).lower().strip()
        # Map aliases and legacy category names onto the canonical 9-category
        # taxonomy (must stay in sync with web/src/lib/types.ts)
        aliases = {
            "concert": "music",
            "konzert": "music",
            "club": "nightlife",
            "party": "nightlife",
            "rave": "nightlife",
            "techno": "nightlife",
            "bar": "nightlife",
            "restaurant": "food",
            "food & drink": "food",
            "essen": "food",
            "art": "culture",
            "kunst": "culture",
            "ausstellung": "culture",
            "exhibition": "culture",
            "gallery": "culture",
            "theater": "culture",
            "theatre": "culture",
            "comedy": "nightlife",
            "film": "culture",
            "kino": "culture",
            "entertainment": "culture",
            "yoga": "outdoors",
            "sport": "outdoors",
            "fitness": "outdoors",
            "wellness": "outdoors",
            "meetup": "meetups",
            "networking": "meetups",
            "social": "meetups",
            "market": "markets",
            "flohmarkt": "markets",
            "flea market": "markets",
            "markt": "markets",
            "wochenmarkt": "food",
            "street food": "food",
            "bauernmarkt": "food",
        }
        resolved = aliases.get(cat, cat)
        return resolved if resolved in VALID_CATEGORIES else None

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: Any) -> str:
        return str(v) if v in {"active", "pending", "rejected"} else "active"


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        # Handle ISO 8601 edge case: 24:00:00 means midnight start of next day
        s = str(value)
        if "T24:00:00" in s:
            from datetime import timedelta
            s = s.replace("T24:00:00", "T00:00:00")
            dt = dateparser.parse(s, dayfirst=True)
            if dt:
                dt = dt + timedelta(days=1)
                if not dt.tzinfo:
                    dt = dt.replace(tzinfo=BERLIN_TZ)
                return dt.astimezone(timezone.utc)
        # Try ISO 8601 first (YYYY-MM-DD) — dayfirst must be False for ISO
        if re.match(r"\d{4}-\d{2}-\d{2}", s):
            dt = dateparser.parse(s, dayfirst=False)
        else:
            dt = dateparser.parse(s, dayfirst=True)
        if dt and not dt.tzinfo:
            # Naive datetimes are Berlin wall-clock time. zoneinfo picks the
            # correct CET/CEST offset per date — a hardcoded +01:00 made every
            # summer midnight render as 01:00 in the app.
            dt = dt.replace(tzinfo=BERLIN_TZ).astimezone(timezone.utc)
        return dt
    except Exception:
        logger.warning("Could not parse datetime: %r", value)
        return None


def _extract_price_cents(price_str: str | None) -> int | None:
    if not price_str:
        return None
    low = price_str.lower()
    if any(word in low for word in ("free", "kostenlos", "gratis", "eintritt frei")):
        return 0
    match = re.search(r"(\d+(?:[.,]\d+)?)", price_str.replace(",", "."))
    if match:
        return int(float(match.group(1)) * 100)
    return None


def make_fingerprint(title: str, venue_name: str, start_time: datetime) -> str:
    """Stable hash for deduplication across sources.

    Uses title + date only (not venue_name) so the same event scraped from
    different sources with slightly different venue names (e.g. "Tresor" vs
    "Tresor / Globus") still produces the same fingerprint.
    """
    date_str = start_time.strftime("%Y-%m-%d")
    raw = f"{title.lower().strip()}|{date_str}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def normalize(raw: dict[str, Any]) -> dict[str, Any] | None:
    """
    Convert a raw scraped dict → normalised event dict ready for Supabase upsert.
    Returns None if the event is invalid (missing required fields).
    """
    try:
        event = RawEvent(**raw)
    except Exception as e:
        logger.warning("Validation error for event %r: %s", raw.get("title"), e)
        return None

    start_time = _parse_dt(event.start_time)
    if start_time is None:
        logger.warning("No parseable start_time for '%s', skipping", event.title)
        return None

    end_time = _parse_dt(event.end_time)

    # Only drop end_time if it's before start_time (clearly bad data)
    if start_time and end_time and end_time < start_time:
        end_time = None

    # Infer price_cents if not provided
    price_cents = event.price_cents
    if price_cents is None:
        price_cents = _extract_price_cents(event.price)

    fingerprint = make_fingerprint(event.title, event.venue_name, start_time)

    return {
        "title": event.title,
        "venue_name": event.venue_name,
        "lat": event.lat,
        "lng": event.lng,
        "neighborhood": event.neighborhood,
        "address": event.address,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat() if end_time else None,
        "category": event.category or "culture",  # fallback
        "subcategory": event.subcategory,
        "tags": event.tags or [],
        "description": event.description,
        "price": event.price,
        "price_cents": price_cents,
        "image_url": event.image_url,
        "source": event.source,
        "source_url": event.source_url,
        "source_id": event.source_id,
        "submitted_by": event.submitted_by,
        "submission_link": event.submission_link,
        "status": event.status,
        "source_tags": event.source_tags or [],
        "quality_score": event.quality_score,
        "fingerprint": fingerprint,
    }
