"""
Geocode events by extracting Berlin postal codes (PLZ) from addresses
and mapping to approximate neighborhood coordinates.
Also includes hardcoded coords for well-known venues.
"""
from __future__ import annotations

import logging
import os
import re
import sys

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)-8s %(message)s", stream=sys.stderr)
logger = logging.getLogger(__name__)

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

# Berlin PLZ -> approximate center coordinates
# Covers all major Berlin postal code areas
PLZ_COORDS = {
    "10115": (52.5316, 13.3837),  # Mitte Nord
    "10117": (52.5163, 13.3890),  # Mitte
    "10119": (52.5296, 13.4098),  # Mitte/Prenzl. Berg
    "10178": (52.5200, 13.4050),  # Mitte Ost
    "10179": (52.5110, 13.4170),  # Mitte/Heinrich-Heine
    "10243": (52.5070, 13.4450),  # Friedrichshain
    "10245": (52.5020, 13.4550),  # Friedrichshain Süd
    "10247": (52.5130, 13.4600),  # Friedrichshain Nord
    "10317": (52.4900, 13.4900),  # Lichtenberg/Rummelsburg
    "10319": (52.4850, 13.5100),  # Karlshorst
    "10365": (52.5100, 13.4900),  # Lichtenberg
    "10369": (52.5250, 13.4700),  # Lichtenberg Nord
    "10405": (52.5350, 13.4250),  # Prenzlauer Berg
    "10407": (52.5300, 13.4400),  # Prenzlauer Berg Ost
    "10409": (52.5450, 13.4400),  # Prenzlauer Berg Nord
    "10435": (52.5370, 13.4100),  # Prenzlauer Berg
    "10437": (52.5470, 13.4100),  # Prenzlauer Berg
    "10439": (52.5500, 13.4100),  # Prenzlauer Berg Nord
    "10551": (52.5270, 13.3400),  # Tiergarten/Moabit
    "10553": (52.5250, 13.3350),  # Moabit
    "10555": (52.5200, 13.3400),  # Moabit
    "10557": (52.5220, 13.3500),  # Tiergarten
    "10623": (52.5080, 13.3220),  # Charlottenburg
    "10625": (52.5100, 13.3100),  # Charlottenburg
    "10627": (52.5060, 13.3030),  # Charlottenburg
    "10629": (52.5000, 13.3100),  # Wilmersdorf
    "10707": (52.4900, 13.3100),  # Wilmersdorf
    "10709": (52.4850, 13.3100),  # Wilmersdorf
    "10711": (52.4900, 13.2900),  # Halensee
    "10715": (52.4800, 13.3300),  # Wilmersdorf
    "10717": (52.4870, 13.3200),  # Wilmersdorf
    "10719": (52.5020, 13.3290),  # Charlottenburg Süd
    "10777": (52.4950, 13.3500),  # Schöneberg
    "10781": (52.4890, 13.3540),  # Schöneberg
    "10783": (52.4920, 13.3630),  # Schöneberg
    "10785": (52.5010, 13.3690),  # Tiergarten/Potsdamer Pl.
    "10787": (52.5050, 13.3430),  # Zoo/Kurfürstendamm
    "10789": (52.5020, 13.3400),  # Charlottenburg Süd
    "10823": (52.4850, 13.3550),  # Schöneberg
    "10825": (52.4830, 13.3500),  # Schöneberg
    "10827": (52.4800, 13.3550),  # Schöneberg
    "10961": (52.4920, 13.3900),  # Kreuzberg
    "10963": (52.4970, 13.3870),  # Kreuzberg
    "10965": (52.4850, 13.3900),  # Kreuzberg Süd
    "10967": (52.4880, 13.4100),  # Kreuzberg
    "10969": (52.5020, 13.4060),  # Kreuzberg/Moritzplatz
    "10997": (52.4990, 13.4350),  # Kreuzberg SO36
    "10999": (52.4950, 13.4250),  # Kreuzberg
    "12043": (52.4830, 13.4300),  # Neukölln
    "12045": (52.4840, 13.4350),  # Neukölln
    "12047": (52.4880, 13.4250),  # Neukölln Nord
    "12049": (52.4800, 13.4220),  # Neukölln/Schillerkiez
    "12051": (52.4720, 13.4350),  # Neukölln
    "12053": (52.4700, 13.4350),  # Neukölln Rollberg
    "12055": (52.4740, 13.4420),  # Neukölln Ost
    "12059": (52.4830, 13.4430),  # Neukölln Ost
    "12099": (52.4700, 13.3850),  # Tempelhof
    "12101": (52.4750, 13.3800),  # Tempelhof
    "12103": (52.4720, 13.3720),  # Tempelhof
    "12163": (52.4600, 13.3300),  # Steglitz
    "12203": (52.4350, 13.3100),  # Lichterfelde
    "12435": (52.4900, 13.4600),  # Treptow
    "12459": (52.4650, 13.4900),  # Oberschöneweide
    "12489": (52.4380, 13.5300),  # Adlershof
    "13051": (52.5600, 13.4700),  # Hohenschönhausen/Malchow
    "13053": (52.5500, 13.4600),  # Hohenschönhausen
    "13088": (52.5550, 13.4700),  # Weißensee
    "13187": (52.5660, 13.4030),  # Pankow
    "13189": (52.5630, 13.4150),  # Pankow
    "13347": (52.5490, 13.3650),  # Wedding
    "13357": (52.5520, 13.3820),  # Gesundbrunnen
    "13407": (52.5700, 13.3450),  # Reinickendorf
    "13409": (52.5640, 13.3600),  # Reinickendorf
    "13507": (52.5900, 13.2800),  # Tegel
    "13581": (52.5350, 13.2000),  # Spandau
    "13597": (52.5370, 13.2100),  # Spandau
    "13599": (52.5430, 13.2100),  # Spandau/Haselhorst
    "14055": (52.5100, 13.2600),  # Westend
    "14057": (52.5100, 13.2800),  # Charlottenburg Nord
    "14059": (52.5200, 13.2900),  # Charlottenburg
    "14467": (52.3950, 13.0620),  # Potsdam Mitte
    "14469": (52.4050, 13.0300),  # Potsdam Nord
    "14471": (52.3880, 13.0100),  # Potsdam Süd
    "14476": (52.4150, 12.9600),  # Potsdam West
    "14482": (52.3900, 13.1000),  # Babelsberg
    "14776": (52.4100, 12.5500),  # Brandenburg an der Havel
}

# Well-known Berlin venues with exact coordinates
KNOWN_VENUES = {
    "://about blank": (52.5078, 13.4569),
    "ACUD MACHT NEU": (52.5333, 13.4010),
    "Acud": (52.5333, 13.4010),
    "Acud Macht NEU": (52.5333, 13.4010),
    "Arena Berlin": (52.4955, 13.4545),
    "Bar jeder Vernunft": (52.4983, 13.3278),
    "Berghain": (52.5110, 13.4430),
    "Berghain | Panorama Bar | Säule": (52.5110, 13.4430),
    "C/O Berlin": (52.5070, 13.3270),
    "Clärchens Ballhaus": (52.5307, 13.3968),
    "Der Weiße Hase": (52.5073, 13.4527),
    "Festsaal Kreuzberg": (52.4960, 13.4423),
    "Fotografiska Berlin": (52.5260, 13.3940),
    "Gropius Bau": (52.5065, 13.3825),
    "HAU 3": (52.4980, 13.3810),
    "Hoppetosse": (52.4955, 13.4545),
    "Humboldt Forum": (52.5188, 13.4017),
    "Humboldthain Club": (52.5520, 13.3860),
    "KitKatClub": (52.5107, 13.4190),
    "Komische Oper im Schillertheater": (52.5130, 13.3100),
    "Lark": (52.5112, 13.4210),
    "M-BIA": (52.5190, 13.4100),
    "Monarch": (52.4990, 13.4210),
    "OHM": (52.5107, 13.4190),
    "Paloma": (52.4990, 13.4210),
    "Philharmonie Berlin & Kammermusiksaal": (52.5098, 13.3698),
    "Punch Line Club": (52.5010, 13.4180),  # Kreuzberg
    "Renate": (52.4975, 13.4660),
    "Sameheads": (52.4815, 13.4260),
    "Schloss Charlottenburg": (52.5191, 13.2920),
    "Schwuz": (52.4732, 13.4400),
    "Silent Green": (52.5450, 13.3660),
    "silent green, Kuppelhalle": (52.5450, 13.3660),
    "So36": (52.4987, 13.4350),
    "Tausend": (52.5210, 13.3867),
    "Tempodrom": (52.5010, 13.3820),
    "Tresor / Globus": (52.5107, 13.4190),
    "Urania": (52.5000, 13.3470),
    "Urania Berlin e.V.": (52.5000, 13.3470),
    "YAAM Berlin": (52.5095, 13.4285),
    "Zeiss-Großplanetarium": (52.5360, 13.4285),
    "Bar Am Ufer": (52.4838, 13.4430),  # Kiehlufer, Neukölln
    "tik - Theater im Kino (Nord)": (52.5135, 13.4575),  # Rigaer Str, Friedrichshain
    "Ritter Butzke (Modus)": (52.5030, 13.4081),
    "Prisma Bar Berlin": (52.5107, 13.4175),
    "Flohmarkt Rathaus Schöneberg": (52.4835, 13.3430),
    "Flohmarkt am Boxhagener Platz": (52.5110, 13.4575),
    "Flohmarkt im Mauerpark": (52.5440, 13.4020),
    "Soda Club": (52.5373, 13.4143),
    "Soda": (52.5373, 13.4143),
    "Kater": (52.5095, 13.4290),
    "90mil": (52.5095, 13.4290),
    "West Germany": (52.4990, 13.4210),
    "Scotty": (52.5000, 13.4200),
    "Loone": (52.4950, 13.4240),
    "FEZ Berlin": (52.4575, 13.5570),
    "Pfefferberg Theater": (52.5310, 13.4120),
    "Sportforum Berlin": (52.5380, 13.4710),
    "PubCrawl Berlin": (52.5200, 13.4050),  # Central Berlin meeting point
    "Silverwings Club": (52.4650, 13.3760),  # Tempelhof
    "BLOCK1": (52.4838, 13.5015),
    "TBA": (52.5000, 13.4000),  # Generic Berlin center
    "TBA - Berlin, Neukölln": (52.4800, 13.4300),
    "Berliner Kriminal Theater": (52.5180, 13.3890),
    "Berliner Kunstmarkt an der Museumsinsel": (52.5210, 13.3960),
    "Forest Cinema": (52.4850, 13.3900),
    "Gesundbrunnen-Center Rooftop": (52.5510, 13.3880),
    "Piscator Saal": (52.5270, 13.3850),
    "RYZON Pop-Up Store Berlin": (52.5250, 13.4050),
    "Ratibor Theater": (52.4980, 13.4250),  # Kreuzberg
    "Stadtbibliothek Reinickendorf - Humboldt Bibliothek": (52.5680, 13.3570),
    "Bühnen Rausch": (52.5200, 13.4050),
    "ÆDEN": (52.4985, 13.4305),
    "Clay Garden Pottery Studio": (52.5100, 13.4200),
    "Clash Kitchens & Bar im NYX Hotel Berlin Köpenick": (52.4450, 13.5750),
    "Madame Claude": (52.4980, 13.4380),
    "Minimal Bar": (52.5135, 13.4600),
    "Lauschangriff": (52.5135, 13.4600),
    "OXI": (52.5100, 13.4900),
    "Void Club": (52.5100, 13.4900),
    "kikisol": (52.4900, 13.4200),
    "freiheit fünfzehn Eventlocation an der Spree": (52.4955, 13.4545),
    "interkosmos - café.bar.utopie": (52.5050, 13.4200),
    "ART Stalker - Kunst + Bar + Events": (52.5300, 13.4000),
    "AQUAHÖFE Berlin (AHB)": (52.5100, 13.3800),
    "\"ocelot, not just another bookstore\"": (52.5275, 13.3985),
    "Teig Talente  - Backkurse für jedes Level": (52.5100, 13.4000),
    "FaF Sommergarten | Filmtheater am Friedrichshain": (52.5260, 13.4340),
    "Test Club": (52.5000, 13.4000),
    "OST": (52.4975, 13.4660),
    "ArtSalon, KiezKultur, Nachbarschaftshaus am Lietzensee": (52.5050, 13.2900),
    "MGH KiezKultur, Herbartstr. linker Nebeneingang 25 14057 Berlin": (52.5100, 13.2850),
}


def extract_plz(address: str) -> str | None:
    """Extract Berlin postal code from address string."""
    if not address:
        return None
    match = re.search(r"\b(1\d{4})\b", address)
    if match:
        return match.group(1)
    return None


def main():
    # Fetch all events missing coords
    data = (
        supabase.table("events")
        .select("id,venue_name,address")
        .is_("lat", "null")
        .limit(1000)
        .execute()
        .data
    )
    logger.info("Found %d events missing coordinates", len(data))

    updated = 0
    failed_venues = set()

    for e in data:
        venue = e["venue_name"]
        address = e.get("address") or ""
        coords = None

        # 1. Check known venues
        if venue in KNOWN_VENUES:
            coords = KNOWN_VENUES[venue]

        # 2. Extract PLZ from address
        if not coords:
            plz = extract_plz(address)
            if plz and plz in PLZ_COORDS:
                coords = PLZ_COORDS[plz]

        # 3. Try extracting PLZ from venue name (some venues have address in name)
        if not coords:
            plz = extract_plz(venue)
            if plz and plz in PLZ_COORDS:
                coords = PLZ_COORDS[plz]

        if coords:
            lat, lng = coords
            supabase.table("events").update({"lat": lat, "lng": lng}).eq("id", e["id"]).execute()
            updated += 1
        else:
            if venue not in failed_venues:
                failed_venues.add(venue)
                logger.info("No coords for: %s | %s", venue, address or "(no address)")

    logger.info("Updated %d events. %d venues still without coords.", updated, len(failed_venues))

    # Final count
    remain = supabase.table("events").select("id", count="exact").is_("lat", "null").execute()
    logger.info("Events still missing coords: %d", remain.count)


if __name__ == "__main__":
    main()
