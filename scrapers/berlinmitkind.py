"""
berlinmitkind.de scraper — family events in Berlin.

Uses WordPress REST API to fetch posts from category "veranstaltungstipp" (ID 68).
Event details are embedded in free-text content. Each post may contain one or
multiple events, each with a bold summary line at the end following a pattern like:
  "DD.MM.YYYY, HH:MM-HH:MM, venue name, website.de"

The scraper extracts individual events from these summary lines.
"""

from __future__ import annotations

import logging
import re
from html import unescape
from typing import Any

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

WP_API = "https://berlinmitkind.de/wp-json/wp/v2/posts"
CATEGORY_ID = 68  # "veranstaltungstipp"
PAGE_SIZE = 50

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
        posts = self._fetch_all_posts()
        logger.info("berlinmitkind: fetched %d posts", len(posts))

        events: list[dict[str, Any]] = []
        for post in posts:
            parsed = self._parse_post(post)
            events.extend(parsed)

        # Filter out old events
        filtered = [e for e in events if str(e.get("start_time", ""))[:10] >= _MIN_DATE]
        logger.info(
            "berlinmitkind: extracted %d events from %d posts (%d filtered as too old)",
            len(filtered), len(posts), len(events) - len(filtered),
        )
        return filtered

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
            event = self._parse_from_excerpt(post_title, excerpt_html, post_link, image_url, content_html)
            return [event] if event else []

        if len(summaries) == 1:
            # Single event post
            event = self._parse_summary_line(
                summaries[0]["text"], post_title, post_link, image_url,
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
                summary["text"], title, post_link, image_url,
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
        heading_pattern = re.compile(
            r"<h[23][^>]*>(.*?)</h[23]>", re.DOTALL | re.IGNORECASE
        )
        headings = [(m.start(), _strip_html(m.group(1)).strip()) for m in heading_pattern.finditer(html)]

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
        self, text: str, title: str, post_link: str,
        image_url: str | None, description: str | None = None,
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
            if any(w in part_clean.lower() for w in (
                "ab ", "für alle", "teilnahme", "anmeldung", "eintritt",
                "tickets", "kinder bis", "jahre",
            )):
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
            "tags": ["family-friendly"],
            "image_url": image_url,
            "source": self.source_name,
        }

    def _extract_section_description(
        self, html: str, summary: dict, all_summaries: list[dict], idx: int,
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
        self, title: str, excerpt_html: str, post_link: str,
        image_url: str | None, content_html: str,
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
