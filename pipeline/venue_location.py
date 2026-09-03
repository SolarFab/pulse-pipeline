"""Pure helpers for deriving structured venue locations.

The original address remains the audit source. These helpers only derive fields
when the input contains evidence for them; they never assume every venue is in
Berlin because the catalogue also contains Brandenburg venues.
"""

from __future__ import annotations

import re
from typing import Any

POSTAL_CODE_RE = re.compile(r"(?<!\d)(\d{5})(?!\d)")
CITY_AFTER_POSTAL_RE = re.compile(
    r"(?<!\d)\d{5}(?!\d)[\s,]+([^,]+?)(?:\s*,\s*(?:Germany|Deutschland))?$",
    re.IGNORECASE,
)

_NON_NEIGHBORHOODS = {
    "berlin",
    "land berlin",
    "deutschland",
    "germany",
}


def clean_location_name(value: object) -> str | None:
    """Trim a geocoder label and remove administrative prefixes."""
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split()).strip(" ,")
    for prefix in ("Bezirk ", "Ortsteil "):
        if cleaned.casefold().startswith(prefix.casefold()):
            cleaned = cleaned[len(prefix) :].strip()
    return cleaned or None


def parse_address(address: object) -> dict[str, str]:
    """Extract a postcode and trailing city from an unstructured address."""
    if not isinstance(address, str) or not address.strip():
        return {}

    result: dict[str, str] = {}
    postal_match = POSTAL_CODE_RE.search(address)
    if postal_match:
        result["postal_code"] = postal_match.group(1)

    city_match = CITY_AFTER_POSTAL_RE.search(address.strip())
    if city_match:
        city = clean_location_name(city_match.group(1))
        if city:
            result["city"] = city
    return result


def _first(address: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = clean_location_name(address.get(key))
        if value:
            return value
    return None


def normalize_neighborhood(value: object, *, city: str | None = None) -> str | None:
    """Return a specific locality, rejecting city/country placeholders."""
    cleaned = clean_location_name(value)
    if not cleaned:
        return None
    rejected = set(_NON_NEIGHBORHOODS)
    if city:
        rejected.add(city.casefold())
    return None if cleaned.casefold() in rejected else cleaned


def fields_from_reverse_result(result: dict[str, Any]) -> dict[str, str | None]:
    """Map a Nominatim reverse result to the venue location model."""
    address = result.get("address")
    if not isinstance(address, dict):
        return {}

    country_code = str(address.get("country_code", "")).casefold()
    if country_code and country_code != "de":
        return {}

    city = _first(address, "city", "town", "municipality", "village")
    district = _first(address, "borough", "city_district", "county")
    # Nominatim's German hierarchy uses ``suburb`` for the searchable Ortsteil
    # (for example Prenzlauer Berg), while ``quarter``/``neighbourhood`` are
    # often tiny Kiez labels. Prefer the stable Ortsteil for user filters.
    neighborhood = _first(address, "suburb", "quarter", "neighbourhood")

    fields: dict[str, str | None] = {
        "postal_code": clean_location_name(address.get("postcode")),
        "city": city,
        "district": district,
        "neighborhood": normalize_neighborhood(neighborhood, city=city),
    }
    if not fields["postal_code"] or not POSTAL_CODE_RE.fullmatch(fields["postal_code"] or ""):
        fields["postal_code"] = None
    return fields
