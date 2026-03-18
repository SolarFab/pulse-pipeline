"""
Berlin Jazz Clubs scraper — powered by jazzity.net.
Scrapes the full programme page (/prog.php) which lists upcoming events
across all Berlin jazz venues in one place.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

PROG_URL = "https://jazzity.net/prog.php"
BASE_URL = "https://jazzity.net"

# Known venue coordinates (from jazzity's Google Maps embeds + manual lookup)
VENUE_INFO: dict[str, dict[str, Any]] = {
    "atrane": {"name": "A-Trane", "address": "Bleibtreustraße 1, 10625 Berlin", "lat": 52.5070, "lng": 13.3190, "neighborhood": "Charlottenburg"},
    "bflat": {"name": "b-flat", "address": "Dircksenstraße 40, 10178 Berlin", "lat": 52.5228, "lng": 13.4094, "neighborhood": "Mitte"},
    "zigzag": {"name": "Zig Zag Jazz Club", "address": "Hauptstraße 12, 10827 Berlin", "lat": 52.4858, "lng": 13.3544, "neighborhood": "Schöneberg"},
    "quasimodo": {"name": "Quasimodo", "address": "Kantstraße 12a, 10623 Berlin", "lat": 52.5048, "lng": 13.3254, "neighborhood": "Charlottenburg"},
    "yorck": {"name": "Yorckschlösschen", "address": "Yorckstraße 15, 10965 Berlin", "lat": 52.4930, "lng": 13.3810, "neighborhood": "Kreuzberg"},
    "schlot": {"name": "Kunstfabrik Schlot", "address": "Invalidenstraße 117, 10115 Berlin", "lat": 52.5320, "lng": 13.3770, "neighborhood": "Mitte"},
    "baden": {"name": "Badenscher Hof", "address": "Badensche Str. 29, 10715 Berlin", "lat": 52.4850, "lng": 13.3330, "neighborhood": "Wilmersdorf"},
    "hatbar": {"name": "The Hat Bar", "address": "Lychener Str. 49, 10437 Berlin", "lat": 52.5430, "lng": 13.4150, "neighborhood": "Prenzlauer Berg"},
    "zosch": {"name": "Zosch", "address": "Tucholskystraße 30, 10117 Berlin", "lat": 52.5260, "lng": 13.3938, "neighborhood": "Mitte"},
    "donau": {"name": "Donau115", "address": "Donaustraße 115, 12043 Berlin", "lat": 52.4830, "lng": 13.4350, "neighborhood": "Neukölln"},
    "sowieso": {"name": "Sowieso", "address": "Weisestraße 24, 12049 Berlin", "lat": 52.4770, "lng": 13.4240, "neighborhood": "Neukölln"},
    "klunkerkranich": {"name": "Klunkerkranich", "address": "Karl-Marx-Str. 66, 12043 Berlin", "lat": 52.4812, "lng": 13.4345, "neighborhood": "Neukölln"},
    "spinnrad": {"name": "Spinnrad", "address": "Wühlischstraße 34, 10245 Berlin", "lat": 52.5070, "lng": 13.4620, "neighborhood": "Friedrichshain"},
    "cookiescream": {"name": "Cookies Cream", "address": "Behrenstraße 55, 10117 Berlin", "lat": 52.5160, "lng": 13.3890, "neighborhood": "Mitte"},
    "bartausend": {"name": "Bar Tausend", "address": "Schiffbauerdamm 11, 10117 Berlin", "lat": 52.5210, "lng": 13.3860, "neighborhood": "Mitte"},
    "tasso": {"name": "Cafe Tasso", "address": "Frankfurter Allee 11, 10247 Berlin", "lat": 52.5130, "lng": 13.4510, "neighborhood": "Friedrichshain"},
    "panda": {"name": "PANDA platforma", "address": "Knaackstraße 97, 10435 Berlin", "lat": 52.5380, "lng": 13.4180, "neighborhood": "Prenzlauer Berg"},
    "jtkarlshorst": {"name": "Jazz Treff Karlshorst", "address": "Treskowallee 112, 10318 Berlin", "lat": 52.4860, "lng": 13.5260, "neighborhood": "Karlshorst"},
    "orania": {"name": "Orania Berlin", "address": "Oranienplatz 17, 10999 Berlin", "lat": 52.5020, "lng": 13.4180, "neighborhood": "Kreuzberg"},
    "kuehlspot": {"name": "Kühlspot Social Club", "address": "Lehderstraße 74-79, 13086 Berlin", "lat": 52.5550, "lng": 13.4530, "neighborhood": "Weißensee"},
    "barbobu": {"name": "Bar Bobu", "address": "Weserstraße 43, 12045 Berlin", "lat": 52.4870, "lng": 13.4370, "neighborhood": "Neukölln"},
    "peppi": {"name": "Peppi Guggenheim", "address": "Karl-Marx-Allee 96, 10243 Berlin", "lat": 52.5170, "lng": 13.4390, "neighborhood": "Friedrichshain"},
    "bierhausurban": {"name": "Bierhaus Urban", "address": "Graefestraße 29, 10967 Berlin", "lat": 52.4900, "lng": 13.4100, "neighborhood": "Kreuzberg"},
    "dujardin": {"name": "Cafe Dujardin", "address": "Böckhstraße 37, 10967 Berlin", "lat": 52.4910, "lng": 13.4170, "neighborhood": "Kreuzberg"},
    "jazzscheune": {"name": "Wittenauer Jazz-Scheune", "address": "Alt-Wittenau 70, 13437 Berlin", "lat": 52.5960, "lng": 13.3260, "neighborhood": "Wittenau"},
}

MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}


class JazzclubsScraper(BaseScraper):
    source_name = "jazzity"

    def scrape(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        try:
            resp = self.get(PROG_URL)
            soup = BeautifulSoup(resp.text, "html.parser")
            events = self._parse_programme(soup)
            logger.info("jazzity: fetched %d events from prog.php", len(events))
        except Exception as e:
            logger.error("jazzity prog.php scrape failed: %s", e)

        return events

    def _parse_programme(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        rows = soup.find_all("div", class_="prog_list")

        for row in rows:
            try:
                event = self._parse_row(row)
                if event:
                    events.append(event)
            except Exception as e:
                logger.debug("jazzity row parse error: %s", e)

        return events

    def _parse_row(self, row) -> dict[str, Any] | None:
        # Use the large screen layout (visible-lg-block) which has the clearest structure
        lg_divs = row.find_all("div", class_="visible-lg-block")
        if len(lg_divs) < 3:
            # Fallback: try xs layout
            return self._parse_row_xs(row)

        # First div: day of week + time
        day_div = lg_divs[0]
        time_text = day_div.find_all("div")
        time_str = "20:00"
        for div in time_text:
            t = div.get_text(strip=True)
            if re.match(r"\d{1,2}:\d{2}", t):
                time_str = t
                break

        # Second div: date number + month/year
        date_div = lg_divs[1]
        date_parts = date_div.find_all("div")
        day_num = ""
        month_year = ""
        if len(date_parts) >= 2:
            day_num = date_parts[0].get_text(strip=True)
            month_year = date_parts[1].get_text(strip=True)  # e.g. "March\n2026"

        if not day_num or not month_year:
            return None

        # Parse month and year from "March\n2026", "March 2026", or "March2026"
        my_parts = re.split(r"[\s\n]+", month_year.strip())
        if len(my_parts) >= 2:
            month_name = my_parts[0]
            year_str = my_parts[1]
        else:
            # No whitespace separator — split at digit boundary: "March2026"
            m = re.match(r"([A-Za-z]+)(\d{4})", month_year.strip())
            if not m:
                return None
            month_name = m.group(1)
            year_str = m.group(2)
        month_num = MONTHS.get(month_name)
        if not month_num:
            return None

        try:
            dt = datetime(int(year_str), month_num, int(day_num),
                         int(time_str.split(":")[0]), int(time_str.split(":")[1]))
            start_time = dt.isoformat()
        except (ValueError, IndexError):
            return None

        # Content div: venue name, event title, description, tags
        # The col-md-7 content div may be a direct lg_div or wrapped inside an <a> tag
        content_div = None
        # First try: find the <a> tag wrapping a visible-lg-block div
        for a_tag in row.find_all("a", href=re.compile(r"/clubs\.php\?club=")):
            inner = a_tag.find("div", class_="visible-lg-block")
            if inner:
                content_div = inner
                break
        # Fallback: third lg div
        if not content_div and len(lg_divs) >= 3:
            content_div = lg_divs[2]

        content_divs = content_div.find_all("div", recursive=False) if content_div else []

        venue_name_text = ""
        title = ""
        description = ""
        tags: list[str] = []

        for i, div in enumerate(content_divs):
            text = div.get_text(strip=True)
            if i == 0:
                venue_name_text = re.sub(r"\s*»\s*$", "", text).strip()
            elif i == 1:
                title = text
            elif i == 2 and not div.find("span", class_="tags"):
                description = text.strip()
            # Collect tags
            for tag_span in div.find_all("span", class_="tags"):
                tags.append(tag_span.get_text(strip=True).lower())

        if not title:
            return None

        # Extract club slug from link
        club_slug = ""
        club_link = row.find("a", href=re.compile(r"/clubs\.php\?club="))
        if club_link:
            href = club_link["href"]
            m = re.search(r"club=(\w+)", href)
            if m:
                club_slug = m.group(1)

        # Look up venue info
        venue = VENUE_INFO.get(club_slug, {})
        final_venue_name = venue.get("name", venue_name_text or "Unknown Venue")

        # External link (venue website for this event)
        source_url = f"{BASE_URL}/clubs.php?club={club_slug}" if club_slug else PROG_URL
        ext_link = None
        last_lg = lg_divs[-1] if len(lg_divs) >= 4 else None
        if last_lg:
            ext_a = last_lg.find("a", href=re.compile(r"^https?://"))
            if ext_a:
                ext_link = ext_a["href"]

        # Build source_id from prog_id if available
        prog_id = ""
        title_attr = row.find("div", attrs={"title": re.compile(r"prog_id:")})
        if title_attr:
            m = re.search(r"prog_id:\s*(\d+)", title_attr["title"])
            if m:
                prog_id = m.group(1)

        source_id = f"jazzity-{prog_id}" if prog_id else f"jazzity-{club_slug}-{dt.strftime('%Y%m%d-%H%M')}"

        return {
            "title": title,
            "venue_name": final_venue_name,
            "address": venue.get("address"),
            "lat": venue.get("lat"),
            "lng": venue.get("lng"),
            "neighborhood": venue.get("neighborhood"),
            "start_time": start_time,
            "end_time": None,
            "description": description[:400] if description else None,
            "price": None,
            "source_url": ext_link or source_url,
            "source_id": source_id,
            "category": "music",
            "subcategory": "jazz-blues",
            "tags": ["jazz", "live-music"] + tags,
            "source_tags": tags.copy(),
            "source": self.source_name,
        }

    def _parse_row_xs(self, row) -> dict[str, Any] | None:
        """Fallback parser using the extra-small screen layout."""
        xs_div = row.find("div", class_="visible-xs-block")
        if not xs_div:
            return None

        divs = xs_div.find_all("div", recursive=False)
        if len(divs) < 2:
            return None

        # Second div: "18 Mar, 19:30, Zig Zag Jazz Club »"
        info_text = divs[1].get_text(strip=True)
        # Pattern: "DD Mon, HH:MM, Venue »"
        m = re.match(r"(\d{1,2})\s+(\w+),\s*(\d{1,2}:\d{2}),\s*(.+?)(?:\s*»)?$", info_text)
        if not m:
            return None

        day = int(m.group(1))
        month_abbr = m.group(2)
        time_str = m.group(3)

        # Map 3-letter month abbreviations
        month_map = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
                     "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}
        month = month_map.get(month_abbr)
        if not month:
            return None

        year = datetime.now().year
        # If month is in the past and we're late in the year, assume next year
        if month < datetime.now().month:
            year += 1

        try:
            dt = datetime(year, month, day,
                         int(time_str.split(":")[0]), int(time_str.split(":")[1]))
        except ValueError:
            return None

        # Title from third div
        title = divs[2].get_text(strip=True) if len(divs) > 2 else None
        if not title:
            return None
        # Remove external link icon text
        title = re.sub(r"\s*$", "", title).strip()

        # Club slug
        club_slug = ""
        club_link = row.find("a", href=re.compile(r"/clubs\.php\?club="))
        if club_link:
            href_match = re.search(r"club=(\w+)", club_link["href"])
            if href_match:
                club_slug = href_match.group(1)

        venue = VENUE_INFO.get(club_slug, {})

        # Tags
        tags: list[str] = []
        for tag_span in xs_div.find_all("span", class_="tags"):
            tags.append(tag_span.get_text(strip=True).lower())

        source_id = f"jazzity-{club_slug}-{dt.strftime('%Y%m%d-%H%M')}"

        return {
            "title": title,
            "venue_name": venue.get("name", m.group(4).strip()),
            "address": venue.get("address"),
            "lat": venue.get("lat"),
            "lng": venue.get("lng"),
            "neighborhood": venue.get("neighborhood"),
            "start_time": dt.isoformat(),
            "end_time": None,
            "description": None,
            "price": None,
            "source_url": f"{BASE_URL}/clubs.php?club={club_slug}" if club_slug else PROG_URL,
            "source_id": source_id,
            "category": "music",
            "subcategory": "jazz-blues",
            "tags": ["jazz", "live-music"] + tags,
            "source_tags": tags.copy(),
            "source": self.source_name,
        }
