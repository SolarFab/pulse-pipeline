"""
berlinmitkind.de scraper — family events in Berlin.

Two data sources:
1. WordPress REST API posts from category "veranstaltungstipp" (ID 68) — curated tips
2. Events Manager RSS feed (?post_type=event) — full calendar with 500+ events

The RSS feed is the primary source (structured date/time/venue).
Blog posts add curated events with richer descriptions.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from html import unescape
from typing import Any

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

WP_API = "https://berlinmitkind.de/wp-json/wp/v2/posts"
CATEGORY_ID = 68  # "veranstaltungstipp"
PAGE_SIZE = 50
EVENT_RSS_URL = "https://berlinmitkind.de/feed/?post_type=event"

# Regex to strip HTML tags
_STRIP_HTML = re.compile(r"<[^>]+>")

# Date patterns found in summary lines
_DATE_RE = re.compile(
    r"(\d{1,2}\.\d{1,2}\.\d{4})"  # DD.MM.YYYY
)
_TIME_RANGE_RE = re.compile(
    r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})"  # HH:MM-HH:MM
)
_SINGLE_TIME_RE = re.compile(
    r"(?<!\d[-–])\b(\d{1,2}:\d{2})\b"  # standalone HH:MM
)

# Price indicators
_FREE_WORDS = ("kostenlos", "kostenfrei", "eintritt frei", "gratis", "free", "kein eintritt")


_MIN_DATE = "2025-01-01"  # skip events before this date


class BerlinMitKindScraper(BaseScraper):
    source_name = "berlinmitkind"

    def scrape(self) -> list[dict[str, Any]]:
        today_str = date.today().isoformat()

        # Source 1: Events Manager RSS feed (primary — structured data, 500+ events)
        rss_events = self._fetch_rss_events()
        logger.info("berlinmitkind: %d events from RSS feed", len(rss_events))

        # Source 2: Blog posts (curated tips with richer descriptions)
        posts = self._fetch_all_posts()
        logger.info("berlinmitkind: fetched %d blog posts", len(posts))
        blog_events: list[dict[str, Any]] = []
        for post in posts:
            parsed = self._parse_post(post)
            blog_events.extend(parsed)
        logger.info("berlinmitkind: %d events from blog posts", len(blog_events))

        # Merge: RSS events + blog events, deduplicate by source_id
        seen_ids: set[str] = set()
        events: list[dict[str, Any]] = []
        for e in rss_events + blog_events:
            sid = e.get("source_id", "")
            if sid not in seen_ids:
                seen_ids.add(sid)
                events.append(e)

        # Filter: future events only
        filtered = [e for e in events if str(e.get("start_time", ""))[:10] >= today_str]
        logger.info(
            "berlinmitkind: %d future events total (%d RSS + %d blog, %d past filtered)",
            len(filtered),
            len(rss_events),
            len(blog_events),
            len(events) - len(filtered),
        )

        # Enrich RSS events that have no description
        self._enrich_descriptions(filtered)

        return filtered

    def _enrich_descriptions(self, events: list[dict[str, Any]]) -> None:
        """Fetch og:description from event pages for events missing descriptions."""
        import time as _time

        need_desc = [e for e in events if not e.get("description") and e.get("source_url")]
        if not need_desc:
            return

        logger.info("berlinmitkind: enriching descriptions for %d events", len(need_desc))
        enriched = 0
        for event in need_desc:
            try:
                resp = self.get(event["source_url"])
                match = re.search(
                    r'<meta\s+property="og:description"\s+content="([^"]+)"',
                    resp.text,
                )
                if match:
                    from html import unescape as html_unescape

                    desc = html_unescape(match.group(1)).strip()
                    if desc and len(desc) > 10:
                        event["description"] = desc[:500]
                        enriched += 1
            except Exception as e:
                logger.debug(
                    "berlinmitkind: description fetch failed for %s: %s", event.get("source_url"), e
                )

            _time.sleep(0.5)

        logger.info(
            "berlinmitkind: enriched %d / %d events with descriptions", enriched, len(need_desc)
        )

    def _fetch_all_posts(self) -> list[dict]:
        posts: list[dict] = []
        page = 1
        while True:
            try:
                data = self.get_json(
                    WP_API,
                    params={
                        "categories": CATEGORY_ID,
                        "per_page": PAGE_SIZE,
                        "page": page,
                        "_fields": "id,title,date,link,excerpt,content",
                        "orderby": "date",
                        "order": "desc",
                    },
                )
            except Exception as e:
                # WP API returns 400 when page is beyond total — stop
                logger.info("berlinmitkind: stopped at page %d (%s)", page, e)
                break

            if not data:
                break

            posts.extend(data)
            if len(data) < PAGE_SIZE:
                break
            page += 1

        return posts

    def _fetch_rss_events(self) -> list[dict[str, Any]]:
        """Fetch events from the Events Manager RSS feed."""
        try:
            resp = self.get(EVENT_RSS_URL)
        except Exception as e:
            logger.error("berlinmitkind: failed to fetch RSS feed: %s", e)
            return []

        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError as e:
            logger.error("berlinmitkind: failed to parse RSS XML: %s", e)
            return []

        events: list[dict[str, Any]] = []
        for item in root.findall(".//item"):
            event = self._parse_rss_item(item)
            if event:
                events.append(event)

        return events

    def _parse_rss_item(self, item: ET.Element) -> dict[str, Any] | None:
        """Parse a single RSS <item> into an event dict.

        RSS description format:
          "DD.MM.YYYY - HH:MM <br/>Venue Name <br/>Street <br/>City"
        or:
          "DD.MM.YYYY - HH:MM-HH:MM <br/>Venue Name <br/>..."
        """
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        pub_date = item.findtext("pubDate", "").strip()
        desc_raw = item.findtext("description", "").strip()

        if not title or not link:
            return None

        # Parse description: split by <br/> to get date/time, venue, address
        desc_text = unescape(desc_raw)
        parts = [p.strip() for p in re.split(r"<br\s*/?>", desc_text) if p.strip()]

        # Part 0: "DD.MM.YYYY - HH:MM" or "DD.MM.YYYY - HH:MM-HH:MM"
        start_time = None
        end_time = None
        venue_name = None
        address = None

        if parts:
            date_line = parts[0]
            # Extract date
            date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", date_line)
            if date_match:
                day, month, year = date_match.groups()
                date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"

                # Extract time range or single time
                time_range = re.search(r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})", date_line)
                single_time = re.search(r"(\d{1,2}:\d{2})", date_line)

                if time_range:
                    start_time = f"{date_str}T{time_range.group(1)}:00"
                    end_time = f"{date_str}T{time_range.group(2)}:00"
                elif single_time:
                    start_time = f"{date_str}T{single_time.group(1)}:00"
                else:
                    start_time = date_str
            elif pub_date:
                # Fallback to pubDate
                try:
                    dt = datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %z")
                    start_time = dt.strftime("%Y-%m-%dT%H:%M:%S")
                except ValueError:
                    return None

        if not start_time:
            return None

        # Part 1: venue name, Part 2+: address parts
        if len(parts) >= 2:
            venue_name = _strip_html(parts[1])
        if len(parts) >= 3:
            address_parts = [_strip_html(p) for p in parts[2:]]
            address = ", ".join(address_parts)

        if not venue_name:
            venue_name = "Berlin"

        # Extract date from link slug for source_id (more stable than title)
        date_from_link = re.search(r"(\d{4}-\d{2}-\d{2})", link)
        date_key = date_from_link.group(1) if date_from_link else start_time[:10]

        return {
            "title": title,
            "venue_name": venue_name,
            "address": address,
            "start_time": start_time,
            "end_time": end_time,
            "description": None,  # RSS has no descriptions
            "price": None,
            "source_url": link,
            "source_id": f"bmk-cal-{title[:40]}-{date_key}",
            "category": "family",
            "subcategory": "family-event",
            "tags": ["family-friendly"],
            "image_url": None,
            "source": self.source_name,
        }

    def _parse_post(self, post: dict) -> list[dict[str, Any]]:
        """Extract events from a single WordPress post."""
        post_title = _strip_html(post.get("title", {}).get("rendered", ""))
        post_link = post.get("link", "")
        content_html = post.get("content", {}).get("rendered", "")
        excerpt_html = post.get("excerpt", {}).get("rendered", "")

        # Extract image from content (first img tag)
        image_url = self._extract_image(content_html)

        # Find all bold summary lines in content
        summaries = self._extract_summaries(content_html)

        if not summaries:
            # No structured summary lines — try to parse from excerpt
            event = self._parse_from_excerpt(
                post_title, excerpt_html, post_link, image_url, content_html
            )
            return [event] if event else []

        if len(summaries) == 1:
            # Single event post
            event = self._parse_summary_line(
                summaries[0]["text"],
                post_title,
                post_link,
                image_url,
                description=self._extract_description(content_html),
                source_url=summaries[0].get("url"),
            )
            return [event] if event else []

        # Roundup post — each summary is a separate event
        excerpt_text = _strip_html(excerpt_html).strip()[:300] if excerpt_html else None
        events = []
        for i, summary in enumerate(summaries):
            title = summary.get("heading") or post_title
            # Try section description, fall back to excerpt
            desc = self._extract_section_description(content_html, summary, summaries, i)
            event = self._parse_summary_line(
                summary["text"],
                title,
                post_link,
                image_url,
                description=desc or excerpt_text,
                source_url=summary.get("url"),
            )
            if event:
                events.append(event)
        return events

    def _extract_summaries(self, html: str) -> list[dict]:
        """Find bold summary lines containing dates.

        Returns list of {"text": "...", "heading": "nearest h2/h3 above or None"}
        """
        results = []

        # Split by bold/strong tags and look for date-containing ones
        # Match <strong>...</strong> or <b>...</b> blocks (potentially spanning tags)
        bold_pattern = re.compile(
            r"<p>\s*<(?:strong|b)>(.*?)</(?:strong|b)>\s*</p>",
            re.DOTALL | re.IGNORECASE,
        )

        # Also match patterns where strong wraps the whole paragraph content
        bold_pattern2 = re.compile(
            r"<(?:strong|b)>(.*?)</(?:strong|b)>",
            re.DOTALL | re.IGNORECASE,
        )

        # Find all headings and their positions for context
        heading_pattern = re.compile(r"<h[23][^>]*>(.*?)</h[23]>", re.DOTALL | re.IGNORECASE)
        headings = [
            (m.start(), _strip_html(m.group(1)).strip()) for m in heading_pattern.finditer(html)
        ]

        # First try paragraph-wrapped bold blocks
        for match in bold_pattern.finditer(html):
            raw_html = match.group(1)
            text = _strip_html(raw_html).strip()
            if _DATE_RE.search(text) and len(text) > 15:
                heading = None
                pos = match.start()
                for h_pos, h_text in reversed(headings):
                    if h_pos < pos:
                        heading = h_text
                        break
                # Extract URL from <a> tags inside the bold block
                url_match = re.search(r'href="(https?://[^"]+)"', raw_html)
                url = url_match.group(1) if url_match else None
                results.append({"text": text, "heading": heading, "url": url})

        if results:
            return results

        # Fallback: look for any bold block containing a date
        for match in bold_pattern2.finditer(html):
            raw_html = match.group(1)
            text = _strip_html(raw_html).strip()
            if _DATE_RE.search(text) and len(text) > 20:
                heading = None
                pos = match.start()
                for h_pos, h_text in reversed(headings):
                    if h_pos < pos:
                        heading = h_text
                        break
                url_match = re.search(r'href="(https?://[^"]+)"', raw_html)
                url = url_match.group(1) if url_match else None
                results.append({"text": text, "heading": heading, "url": url})

        # Deduplicate (some summaries might match both patterns)
        seen = set()
        deduped = []
        for r in results:
            if r["text"] not in seen:
                seen.add(r["text"])
                deduped.append(r)
        return deduped

    def _parse_summary_line(
        self,
        text: str,
        title: str,
        post_link: str,
        image_url: str | None,
        description: str | None = None,
        source_url: str | None = None,
    ) -> dict[str, Any] | None:
        """Parse a bold summary line into an event dict.

        Examples:
          "04.04.2026, 14:00-18:00, Teilnahme kostenlos, potsdamerplatz.de"
          "11.12.2025, 18:00, ab 13 Jahren, Theater Strahl, theaterstrahl.de"
          "20.09.-02.11.2025, NABU-Naturschutzzentrum, storchenschmiede.de"
        """
        # Extract date
        date_match = _DATE_RE.search(text)
        if not date_match:
            return None

        date_str = date_match.group(1)  # DD.MM.YYYY
        day, month, year = date_str.split(".")
        start_date = f"{year}-{month}-{day}"

        # Check for a second date (date range)
        end_date = None
        # Pattern: DD.MM.YYYY–DD.MM.YYYY or DD.MM.-DD.MM.YYYY
        range_match = re.search(
            r"(\d{1,2}\.\d{1,2}\.\d{4})\s*[-–]\s*(\d{1,2}\.\d{1,2}\.\d{4})", text
        )
        if range_match:
            end_parts = range_match.group(2).split(".")
            end_date = f"{end_parts[2]}-{end_parts[1]}-{end_parts[0]}"

        # Extract time
        start_time_str = None
        end_time_str = None
        time_range = _TIME_RANGE_RE.search(text)
        if time_range:
            start_time_str = time_range.group(1)
            end_time_str = time_range.group(2)
        else:
            single_time = _SINGLE_TIME_RE.search(text)
            if single_time:
                start_time_str = single_time.group(1)

        # Build ISO datetime
        if start_time_str:
            start_time = f"{start_date}T{start_time_str}:00"
        else:
            start_time = start_date

        end_time = None
        if end_time_str:
            target_date = end_date or start_date
            end_time = f"{target_date}T{end_time_str}:00"
        elif end_date:
            end_time = end_date

        # Extract price
        price = None
        text_lower = text.lower()
        for word in _FREE_WORDS:
            if word in text_lower:
                price = "Free"
                break

        # Extract venue — split by commas, skip date/time/price/url parts
        parts = [p.strip() for p in text.split(",")]
        venue_name = None
        for part in parts:
            part_clean = part.strip()
            # Skip parts that are: dates, times, prices, URLs, age restrictions, short words
            if _DATE_RE.search(part_clean):
                continue
            if re.search(r"\d{1,2}:\d{2}", part_clean):
                continue
            if any(w in part_clean.lower() for w in _FREE_WORDS):
                continue
            if any(
                w in part_clean.lower()
                for w in (
                    "ab ",
                    "für alle",
                    "teilnahme",
                    "anmeldung",
                    "eintritt",
                    "tickets",
                    "kinder bis",
                    "jahre",
                )
            ):
                continue
            if re.search(r"\w+\.\w{2,3}$", part_clean):  # looks like a URL
                continue
            if len(part_clean) < 3:
                continue
            # Skip day-of-week patterns like "Di-Fr", "Mo/Di"
            if re.match(r"^(Mo|Di|Mi|Do|Fr|Sa|So)[/\-:,]", part_clean):
                continue
            # Skip standalone numbers/date fragments like "18.", "11.", "29./30.11.", "11.01."
            if re.match(r"^\d{1,2}[\./]", part_clean):
                continue
            # Skip "verschiedene Termine/Uhrzeiten" patterns
            if "verschiedene" in part_clean.lower() and any(
                w in part_clean.lower() for w in ("termine", "uhrzeiten", "vorstellung")
            ):
                continue
            # This is likely the venue
            venue_name = part_clean
            break

        if not venue_name:
            venue_name = "Berlin"

        return {
            "title": title,
            "venue_name": venue_name,
            "start_time": start_time,
            "end_time": end_time,
            "description": description,
            "price": price,
            "source_url": source_url or post_link,
            "source_id": f"bmk-{title[:40]}-{start_date}",
            "category": "family",
            "subcategory": "family-event",
            "tags": ["family-friendly"],
            "image_url": image_url,
            "source": self.source_name,
        }

    def _extract_section_description(
        self,
        html: str,
        summary: dict,
        all_summaries: list[dict],
        idx: int,
    ) -> str | None:
        """Extract description text from the section above a summary line in a roundup post."""
        heading = summary.get("heading")
        if not heading:
            return None
        # Find the heading position in HTML
        heading_escaped = re.escape(heading)
        h_match = re.search(rf"<h[23][^>]*>[^<]*{heading_escaped}", html, re.IGNORECASE)
        if not h_match:
            return None
        start_pos = h_match.end()
        # Find the summary text position
        summary_escaped = re.escape(summary["text"][:30])
        s_match = re.search(summary_escaped, _strip_html(html[start_pos:]))
        end_pos = start_pos + s_match.start() if s_match else start_pos + 1000
        section = html[start_pos:end_pos]
        # Extract paragraph text
        paragraphs = re.findall(r"<p>(.*?)</p>", section, re.DOTALL)
        texts = [_strip_html(p).strip() for p in paragraphs if len(_strip_html(p).strip()) > 15]
        return " ".join(texts)[:500] if texts else None

    def _parse_from_excerpt(
        self,
        title: str,
        excerpt_html: str,
        post_link: str,
        image_url: str | None,
        content_html: str,
    ) -> dict[str, Any] | None:
        """Fallback: parse event from excerpt when no bold summary found."""
        excerpt = _strip_html(excerpt_html).strip()
        if not excerpt:
            return None

        # Try to extract date from excerpt start
        date_match = _DATE_RE.search(excerpt[:30])
        if not date_match:
            return None

        date_str = date_match.group(1)
        day, month, year = date_str.split(".")
        start_date = f"{year}-{month}-{day}"

        return {
            "title": title,
            "venue_name": "Berlin",
            "start_time": start_date,
            "end_time": None,
            "description": excerpt[:500] if excerpt else None,
            "price": None,
            "source_url": post_link,
            "source_id": f"bmk-{title[:40]}-{start_date}",
            "category": "family",
            "subcategory": "family-event",
            "tags": ["family-friendly"],
            "image_url": image_url,
            "source": self.source_name,
        }

    def _extract_description(self, html: str) -> str | None:
        """Extract first few paragraphs as description."""
        paragraphs = re.findall(r"<p>(.*?)</p>", html, re.DOTALL)
        text_parts = []
        for p in paragraphs[:3]:
            text = _strip_html(p).strip()
            if text and len(text) > 20:
                text_parts.append(text)
        return " ".join(text_parts)[:800] if text_parts else None

    def _extract_image(self, html: str) -> str | None:
        """Extract first image URL from content."""
        match = re.search(r'<img[^>]+src="([^"]+)"', html)
        if match:
            url = match.group(1)
            # Skip tiny icons/tracking pixels
            if "1x1" not in url and "pixel" not in url:
                return url
        return None


def _strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities."""
    return unescape(_STRIP_HTML.sub("", text)).strip()
