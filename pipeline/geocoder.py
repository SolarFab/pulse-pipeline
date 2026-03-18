"""
Batch geocoder — fills in lat/lng for events that have an address but no coordinates.
Uses OpenStreetMap Nominatim (free, 1 req/sec rate limit).
"""

from __future__ import annotations

import logging
import os
import re
import time

import httpx
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "Whatsupp/1.0 (Berlin event discovery app, contact@whatsupp.app)"}


def _get_supabase():
    """Create a fresh Supabase client (avoids stale connections on long runs)."""
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )

# Manual lookup for well-known venues that Nominatim can't resolve.
# Checked and verified coordinates — add new venues as needed.
VENUE_COORDINATES: dict[str, tuple[float, float]] = {
    # --- Theaters ---
    "GRIPS Theater Hansaplatz": (52.5167, 13.3397),
    "GRIPS Theater Podewil": (52.5155, 13.4130),
    "FELD – Theater für junges Publikum": (52.4925, 13.3530),
    "HAU1 Hebbel am Ufer": (52.5044, 13.3828),
    "Theater Strahl": (52.5155, 13.4130),  # at Podewil
    "Theater an der Parkaue": (52.5225, 13.4749),
    "Theater Morgenstern": (52.4870, 13.3680),
    "Deutsche Oper Berlin – Tischlerei": (52.5158, 13.3262),
    "Deutsche Oper Berlin": (52.5158, 13.3262),
    "Komische Oper Berlin im Schillertheater": (52.5133, 13.3149),
    "Komische Oper im Schillertheater": (52.5133, 13.3149),
    "Heimathafen Neukölln": (52.4826, 13.4346),
    "Pfefferberg Theater": (52.5320, 13.4134),
    "Hans Otto Theater Potsdam": (52.4034, 13.0656),
    "Schaubude Berlin": (52.5292, 13.4138),
    "Wintergarten Varieté": (52.5068, 13.3432),
    "Friedrichstadtpalast Berlin": (52.5238, 13.3878),
    "Kulturhaus Spandau im Theatersaal": (52.5355, 13.2055),
    # --- Museums & galleries ---
    "Kunstquartier Bethanien": (52.5022, 13.4239),
    "Berlinische Galerie": (52.5026, 13.4107),
    "Kurt Mühlenhaupt Museum": (52.4880, 13.3830),
    "Museum für Naturkunde": (52.5304, 13.3797),
    "museumfuernaturkunde.berlin": (52.5304, 13.3797),
    "Labyrinth Kindermuseum Berlin": (52.5528, 13.3599),
    "Dokumentationszentrum Flucht": (52.5070, 13.3916),
    "Stasi-Zentrale. Campus für Demokratie": (52.5141, 13.4872),
    "Futurium": (52.5239, 13.3736),
    # --- Concert & event venues ---
    "ATZE Musiktheater": (52.5525, 13.3594),
    "Konzerthaus Berlin": (52.5138, 13.3919),
    "Staatsoper Berlin": (52.5168, 13.3942),
    "Haus der Berliner Festspiele": (52.4920, 13.3418),
    "SO 36": (52.4989, 13.4332),
    "YAAM Berlin": (52.5103, 13.4279),
    "Nikolaisaal Potsdam": (52.3964, 13.0613),
    "Probensaal der Alten Bibliothek": (52.5170, 13.3930),
    # --- Shopping & leisure ---
    "The Playce am Potsdamer Platz": (52.5096, 13.3761),
    "Ostern in The Playce am Potsdamer Platz": (52.5096, 13.3761),
    "Messe Berlin": (52.5005, 13.2694),
    "SPRUNG.RAUM Trampolin Park": (52.4265, 13.3700),
    "BMW Motorrad Welt": (52.5395, 13.2183),
    "Modulor GmbH": (52.5000, 13.4100),
    # --- Parks & outdoor ---
    "Botanischer Garten Berlin": (52.4537, 13.3088),
    "Britzer Garten": (52.4310, 13.4000),
    "Gärten der Welt": (52.5395, 13.5757),
    "Tempelhofer Feld": (52.4733, 13.4017),
    "Park am Gleisdreieck": (52.4978, 13.3754),
    "Tierpark Berlin": (52.5070, 13.5295),
    "Domäne Dahlem": (52.4578, 13.2849),
    "Museumsdorf Düppel": (52.4105, 13.2305),
    "Natur Park Südgelände": (52.4638, 13.3656),
    "Volkspark Potsdam": (52.4055, 13.0389),
    "Großer Wiesenpark Volkspark Potsdam": (52.4055, 13.0389),
    "Schlosspark Schönhausen": (52.5764, 13.4024),
    "Görlitzer Park": (52.4950, 13.4370),
    "Start des Kinderfestes im Görlitzer Park": (52.4950, 13.4370),
    # --- FEZ & Wuhlheide ---
    "FEZ-Berlin": (52.4570, 13.5350),
    "Astrid-Lindgren-Bühne im FEZ-Berlin": (52.4570, 13.5350),
    "GEOlino LIVE auf der Parkbühne Wuhlheide": (52.4590, 13.5345),
    # --- Other Berlin venues ---
    "Winterquartier im Nåpoleon Komplex": (52.5029, 13.4504),
    "Napoleon Komplex": (52.5029, 13.4504),
    "Historischer Lokschuppen mit Werkbereich": (52.4590, 13.5120),
    "Holzmarkt 25": (52.5098, 13.4209),
    "Holzmarkt": (52.5098, 13.4209),
    "ufaFabrik": (52.4518, 13.3674),
    "Theatersaal ufaFabrik": (52.4518, 13.3674),
    "Kaiser-Wilhlem-Gedächntniskirche": (52.5046, 13.3352),
    "Kaiser-Wilhelm-Gedächtniskirche": (52.5046, 13.3352),
    "Filmtheater am Friedrichshain": (52.5271, 13.4415),
    "Strandbad Wendenschloss": (52.4183, 13.5763),
    "Strandbad Orankesee": (52.5581, 13.4908),
    "Archenhold-Sternwarte": (52.4872, 13.4779),
    "DARK MATTER": (52.5045, 13.3412),
    "Felleshus": (52.5096, 13.3635),
    "BUCHBOX! am Helmholzplatz": (52.5415, 13.4190),
    "Pankebuch": (52.5690, 13.4050),
    "Pankebuch – Die schönsten Bücher des Nordens": (52.5690, 13.4050),
    "Bebelplatz": (52.5167, 13.3938),
    "Nikolaiviertel Berlin-Mitte": (52.5158, 13.4078),
    "Bundeskanzleramt": (52.5200, 13.3694),
    "Wiese hinter dem Besucherzentrum": (52.5200, 13.3694),
    "Zitadelle Spandau": (52.5434, 13.2131),
    "Flughafen Tempelhof": (52.4733, 13.4017),
    "Berlin Hauptbahnhof": (52.5251, 13.3694),
    "Treffpunkt: Hauptbahnhof": (52.5251, 13.3694),
    "JuBi im Willy-Brandt-Haus": (52.4961, 13.3879),
    "Museumsinsel Berlin": (52.5210, 13.3969),
    "Hans-Rosenthal-Platz": (52.4875, 13.3440),
    "Brandenburger Tor/Straße des 17. Juni": (52.5163, 13.3777),
    # --- Safe-Hub ---
    "Safe-Hub Sportplatz": (52.5539, 13.3653),
    # --- Brandenburg ---
    "Burg Beeskow": (52.1732, 14.2474),
    "Neustädter Gestüte": (52.8466, 12.4505),
    "Schloss & Gut Liebenberg": (52.8710, 13.2290),
    "Sport- und Erholungspark Strausberg": (52.5800, 13.8850),
    "Rennbahn Hoppegarten": (52.5060, 13.6580),
    "Ökowerk": (52.4898, 13.2373),
    "Museumsdorf Glashütte": (52.3450, 13.5260),
    # --- LabSaal ---
    "LabSaal": (52.6125, 13.3510),
    "LabSaal und andere Spielorte": (52.6125, 13.3510),
    # --- Bookshops & community ---
    "Stiftung für Mensch und Umwelt": (52.4550, 13.3440),
    "Jugend in Berliner Wäldern e.V.": (52.4700, 13.2600),
    # --- Misc ---
    "ComicInvasion": (52.5108, 13.3880),  # Museum für Kommunikation
    "Ziegelei 10": (52.5285, 13.3710),
}

# Cache: venue_name → (lat, lng) to avoid re-geocoding the same venue
_venue_cache: dict[str, tuple[float, float] | None] = {}


def geocode(query: str) -> tuple[float, float] | None:
    """Geocode an address string to (lat, lng) using Nominatim."""
    try:
        resp = httpx.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "de"},
            headers=HEADERS,
            timeout=10,
        )
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:
        logger.debug("Geocode failed for %r: %s", query, e)
    return None


_SKIP_VENUE_PATTERNS = (
    "berlinweit", "berlin-weit", "verschiedene", "diverse", "mehrere",
    "viele events", "viele veranstaltung", "rund ", "immer ",
    "keine anmeldung", "veranstaltungsinfos", "für familien",
    "für alle", "termine", "uhrzeiten", "vorstellung",
    "sportfeste in", "angebote",
)


def _is_geocodable(venue: str) -> bool:
    """Check if a venue name is specific enough to geocode meaningfully."""
    if not venue or venue == "Berlin":
        return False
    low = venue.lower()
    if any(p in low for p in _SKIP_VENUE_PATTERNS):
        return False
    # Skip age ranges like "5-13 Jahre", day patterns like "Di-Fr"
    if re.match(r"^\d+-\d+\s", venue):
        return False
    if re.match(r"^(Mo|Di|Mi|Do|Fr|Sa|So)[/\-:,]", venue):
        return False
    # Skip standalone date fragments
    if re.match(r"^\d{1,2}\.\/?", venue):
        return False
    return True


def geocode_event(event: dict) -> tuple[float, float] | None:
    """Try geocoding an event, using manual lookup, address, then venue name + Berlin."""
    venue = event.get("venue_name", "")
    address = event.get("address", "")

    # Strategy 0: Manual venue lookup (instant, no API call)
    if venue and venue in VENUE_COORDINATES:
        return VENUE_COORDINATES[venue]

    # Skip vague/non-geocodable venues (unless they have a specific address)
    if not address and not _is_geocodable(venue):
        return None

    # Check cache first
    cache_key = f"{venue}|{address}"
    if cache_key in _venue_cache:
        return _venue_cache[cache_key]

    result = None

    # Strategy 1: Full address
    if address and len(address) > 5:
        # Clean up address: remove semicolons used by RA
        clean_addr = address.replace(";", ",")
        result = geocode(clean_addr)

    # Strategy 2: Address + Berlin (in case address lacks city)
    if not result and address and len(address) > 5:
        result = geocode(f"{address}, Berlin, Germany")

    # Strategy 3: Venue name + Berlin
    if not result and venue:
        result = geocode(f"{venue}, Berlin, Germany")

    _venue_cache[cache_key] = result
    return result


def geocode_inline(events: list[dict]) -> list[dict]:
    """Geocode events inline during the pipeline. Mutates events in place.
    Only geocodes events that are missing lat/lng. No rate-limit sleep for cached hits.
    Skips geocoding for large batches (>500) to avoid hour-long waits."""
    need_geocoding = sum(1 for e in events if not (e.get("lat") and e.get("lng")))
    if need_geocoding > 500:
        logger.info("Skipping inline geocoding for %d events (too many). Run geocoder separately.", need_geocoding)
        logger.info("Inline geocoded 0 / %d events", len(events))
        return events
    count = 0
    for event in events:
        if event.get("lat") and event.get("lng"):
            continue
        coords = geocode_event(event)
        if coords:
            event["lat"], event["lng"] = coords
            count += 1
        # Nominatim rate limit: 1 req/sec (cache avoids redundant calls)
        time.sleep(2.0)
    logger.info("Inline geocoded %d / %d events", count, len(events))
    return events


def run(limit: int = 500, dry_run: bool = False):
    """Geocode events missing coordinates."""
    client = _get_supabase()
    # Fetch events without lat/lng that have an address or venue_name
    data = (
        client.table("events")
        .select("id,venue_name,address,lat,lng")
        .is_("lat", "null")
        .limit(limit)
        .execute()
        .data
    )

    logger.info("Found %d events to geocode", len(data))

    updated = 0
    failed = 0

    for event in data:
        coords = geocode_event(event)
        if coords:
            lat, lng = coords
            if not dry_run:
                try:
                    client.table("events").update(
                        {"lat": lat, "lng": lng}
                    ).eq("id", event["id"]).execute()
                except Exception as e:
                    logger.warning("DB update failed, reconnecting: %s", e)
                    client = _get_supabase()
                    client.table("events").update(
                        {"lat": lat, "lng": lng}
                    ).eq("id", event["id"]).execute()
            updated += 1
            logger.debug(
                "Geocoded: %s → (%.4f, %.4f)",
                event.get("venue_name", "?"),
                lat,
                lng,
            )
        else:
            failed += 1
            logger.debug("Failed to geocode: %s / %s", event.get("venue_name"), event.get("address"))

        # Nominatim rate limit: 1 req/sec (but we cache, so often faster)
        time.sleep(2.0)

    logger.info("Geocoded %d events, %d failed", updated, failed)
    return updated, failed


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)-8s %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run(limit=args.limit, dry_run=args.dry_run)
