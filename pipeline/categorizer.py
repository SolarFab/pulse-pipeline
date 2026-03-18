"""
Categorizer: uses Claude API to assign category + tags to events
that couldn't be categorized from source metadata alone.

Returns bilingual tags (EN + DE keywords) so that new German keywords
can be auto-expanded into the taxonomy keyword dictionary.

Uses batched requests (10 events/call) + prompt caching to minimize cost.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Collect new keyword mappings discovered by the LLM
_new_keyword_mappings: list[dict[str, Any]] = []

CATEGORIES = ["music", "nightlife", "culture", "food", "markets", "workshops", "meetups", "outdoors", "family"]

SUBCATEGORIES = {
    "music": ["jazz-blues", "electronic", "classical", "rock-pop", "hip-hop", "live-concert", "world-folk", "latin"],
    "nightlife": ["club-night", "bar-event", "party", "comedy", "karaoke"],
    "culture": ["exhibition", "theater", "cinema", "reading", "gallery", "festival"],
    "food": ["brunch", "tasting", "pop-up", "dining-event"],
    "markets": ["flea-market", "weekly-market", "design-market", "food-market"],
    "workshops": ["creative-workshop", "language", "digital-skills", "dance-class", "craft"],
    "meetups": ["networking", "community", "tech-startup", "talk-panel", "activism"],
    "outdoors": ["walking-tour", "sports", "yoga-fitness", "bike-tour", "outdoor-cinema"],
    "family": ["kids-program", "family-event", "playground", "museum-for-kids"],
}

SYSTEM_PROMPT = """\
You are a Berlin event categorization assistant. Given event data, assign the best category, subcategory, and relevant English tags.

Categories (pick exactly one):
- music: concerts, live bands, jazz, classical, electronic, singer-songwriter
- nightlife: club nights, raves, DJ sets, parties, bar events, comedy, karaoke
- culture: exhibitions, theater, cinema, readings, galleries, festivals
- food: brunch, tastings, pop-up dinners, dining events
- markets: flea markets, weekly markets, design markets, food markets
- workshops: creative workshops, language classes, digital skills, dance classes, craft
- meetups: networking, community events, tech/startup, talks/panels, activism
- outdoors: walking tours, sports, yoga/fitness, bike tours, outdoor cinema
- family: kids programs, family events, playgrounds, museums for kids

Subcategories per category:
- music: jazz-blues, electronic, classical, rock-pop, hip-hop, live-concert, world-folk, latin
- nightlife: club-night, bar-event, party, comedy, karaoke
- culture: exhibition, theater, cinema, reading, gallery, festival
- food: brunch, tasting, pop-up, dining-event
- markets: flea-market, weekly-market, design-market, food-market
- workshops: creative-workshop, language, digital-skills, dance-class, craft
- meetups: networking, community, tech-startup, talk-panel, activism
- outdoors: walking-tour, sports, yoga-fitness, bike-tour, outdoor-cinema
- family: kids-program, family-event, playground, museum-for-kids

CATEGORIZATION RULES — follow these strictly:
1. Categorize by the PRIMARY ACTIVITY the attendee goes for, not the venue type.
2. Live music (bands, concerts, singer-songwriter) at any venue → "music", even if it's at a bar.
3. DJ sets / techno / dance-focused events → "nightlife", even if there's live music too.
4. Any market (flea, food, farmers, craft, design) → "markets", even if food is sold there.
5. Art exhibitions, museum shows, gallery openings → "culture", even if there's a DJ or party after.
6. Street food markets → "markets" (NOT "food"). The market IS the event.
7. Food events at restaurants, pop-ups, tastings → "food".
8. Comedy / stand-up / kabarett → "nightlife" (subcategory: comedy).
9. Yoga, fitness, sports → "outdoors" (not workshops).
10. If the title or venue contains "Markt", "Market", "Flohmarkt" → almost certainly "markets".
11. Events that are not real public events (police stations, administrative services) → quality_score: 0.0.

TAG RULES — very important:
- Tags MUST be in English, even if the event description is in German.
- For each tag, also provide the German keyword(s) that led you to assign it — this is used to auto-expand our keyword dictionary.
- Use existing tags when they fit. Common tags include: painting, sculpture, photography, architecture, history, berlin-history, wwii, migration, science, astronomy, climate, technology, coding, finance, poetry, fairy-tales, storytelling, literature, dance, yoga, table-tennis, football, gymnastics, running, swimming, climbing, cycling, lego, gaming, board-games, role-playing, puzzle, language-exchange, german-language, counseling, self-help, repair-cafe, swap-meet, cooking, wine, beer, pottery, sewing, knitting, woodwork, upcycling, printing, free, outdoor, queer, family-friendly, accessible, english-friendly, inclusive.
- You MAY create NEW tags if none of the existing ones fit. New tags should be lowercase, hyphenated English words (e.g., "calligraphy", "circus", "magic-show", "bird-watching").
- Include specific genre/topic tags (e.g., "impressionism", "cubism", "baroque", "neuroscience").
- Include vibe/attribute tags where appropriate (e.g., "free", "outdoor", "queer", "accessible").
- Max 5 tags per event.

You will receive a JSON array of events. Return a JSON array of results in the SAME ORDER.
Each result:
{"category": "...", "subcategory": "...", "tags": [{"en": "tag", "de": ["keyword1"]}, ...], "quality_score": 0.0-1.0}

Quality score: 1.0 = complete data with rich description, 0.5 = minimal data, 0.0 = unusable/not a real event.

Return ONLY the JSON array, no explanation."""

BATCH_SIZE = 10  # events per API call


def _make_event_payload(event: dict[str, Any]) -> dict[str, Any]:
    """Extract the fields we send to the LLM."""
    return {
        "title": event.get("title"),
        "venue_name": event.get("venue_name"),
        "description": (event.get("description") or "")[:800],  # cap per-event to fit batch
        "price": event.get("price"),
        "source": event.get("source"),
        "existing_category": event.get("category"),
        "existing_tags": event.get("tags"),
    }


def _parse_tags(raw_tags: list) -> list[str]:
    """Parse bilingual tags and collect keyword mappings."""
    en_tags = []
    for tag_entry in raw_tags:
        if isinstance(tag_entry, dict):
            en_tag = tag_entry.get("en", "")
            de_keywords = tag_entry.get("de", [])
            if en_tag:
                en_tags.append(en_tag)
                if de_keywords:
                    _new_keyword_mappings.append({
                        "tag": en_tag,
                        "de": de_keywords if isinstance(de_keywords, list) else [de_keywords],
                    })
        elif isinstance(tag_entry, str):
            en_tags.append(tag_entry)
    return en_tags


def _apply_result(event: dict[str, Any], result: dict[str, Any]) -> None:
    """Apply a single LLM result to an event dict (in-place)."""
    if result.get("category") in CATEGORIES:
        event["category"] = result["category"]
        sub = result.get("subcategory")
        valid_subs = SUBCATEGORIES.get(event["category"], [])
        if sub and sub in valid_subs:
            event["subcategory"] = sub
        elif not event.get("subcategory"):
            event["subcategory"] = sub

    raw_tags = result.get("tags") or []
    en_tags = _parse_tags(raw_tags)
    event["tags"] = en_tags or event.get("tags") or []
    event["quality_score"] = result.get("quality_score")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _categorize_batch_call(client: anthropic.Anthropic, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Send a batch of events to Claude and return parsed results.
    Uses prompt caching for the system prompt.
    """
    payloads = [_make_event_payload(e) for e in events]
    user_content = json.dumps(payloads, ensure_ascii=False)

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_content}],
    )

    raw = message.content[0].text.strip()
    # Strip markdown code fences
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    results = json.loads(raw)

    if not isinstance(results, list):
        # Single result returned instead of array — wrap it
        results = [results]

    return results


def categorize_event(event: dict[str, Any]) -> dict[str, Any]:
    """
    Categorize a single event via LLM. Kept for backwards compatibility.
    Prefer categorize_batch() for efficiency.
    """
    if event.get("category") and event.get("subcategory") and event.get("tags") and event.get("quality_score") is not None:
        return event

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("No ANTHROPIC_API_KEY — skipping categorization for '%s'", event.get("title"))
        return event

    client = anthropic.Anthropic(api_key=api_key)
    try:
        results = _categorize_batch_call(client, [event])
        if results:
            _apply_result(event, results[0])
    except Exception as e:
        logger.error("Categorization failed for '%s': %s", event.get("title"), e)

    return event


def categorize_batch(events: list[dict[str, Any]], max_llm: int = 2500) -> list[dict[str, Any]]:
    """Categorize a list of events. Skips already-categorized ones."""
    needs_categorization = [
        e for e in events
        if not (e.get("category") and e.get("subcategory") and e.get("tags"))
    ]
    already_done = [
        e for e in events
        if e.get("category") and e.get("subcategory") and e.get("tags")
    ]

    logger.info("Categorizing %d events (%d already done)", len(needs_categorization), len(already_done))

    if len(needs_categorization) > max_llm:
        logger.info(
            "Too many to categorize (%d > %d). Run categorizer separately or increase max_llm.",
            len(needs_categorization), max_llm,
        )
        return events

    if not needs_categorization:
        return events

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("No ANTHROPIC_API_KEY — skipping LLM categorization")
        return events

    client = anthropic.Anthropic(api_key=api_key)
    results = []

    # Process in batches of BATCH_SIZE
    for i in range(0, len(needs_categorization), BATCH_SIZE):
        batch = needs_categorization[i : i + BATCH_SIZE]
        try:
            llm_results = _categorize_batch_call(client, batch)

            # Apply results to events
            for j, event in enumerate(batch):
                if j < len(llm_results):
                    _apply_result(event, llm_results[j])
                results.append(event)

        except json.JSONDecodeError as e:
            logger.warning("Batch %d: JSON parse error: %s", i // BATCH_SIZE, e)
            # Add events without LLM enrichment
            results.extend(batch)
        except Exception as e:
            logger.error("Batch %d failed after retries: %s", i // BATCH_SIZE, e)
            results.extend(batch)

        processed = min(i + BATCH_SIZE, len(needs_categorization))
        if processed % 50 == 0 or processed == len(needs_categorization):
            logger.info("Categorized %d / %d", processed, len(needs_categorization))

    # Auto-expand: save new keyword mappings discovered by the LLM
    if _new_keyword_mappings:
        save_new_keywords(_new_keyword_mappings)

    return results + already_done


def save_new_keywords(mappings: list[dict[str, Any]]) -> None:
    """
    Save new LLM-discovered keyword mappings to a JSON file.
    These can be reviewed and merged into taxonomy.py's TAG_KEYWORDS.
    """
    from pipeline.taxonomy import TAG_KEYWORDS

    # Deduplicate and filter out keywords we already have
    existing_keywords: set[str] = set()
    for kws in TAG_KEYWORDS.values():
        for kw in kws:
            existing_keywords.add(kw.lower())

    new_entries: dict[str, set[str]] = {}
    for mapping in mappings:
        tag = mapping["tag"]
        for de_kw in mapping.get("de", []):
            if de_kw.lower() not in existing_keywords:
                if tag not in new_entries:
                    new_entries[tag] = set()
                new_entries[tag].add(de_kw.lower())

    if not new_entries:
        logger.info("No new keywords discovered by LLM")
        return

    # Save to JSON for review + auto-merge
    output_path = Path(__file__).parent.parent / "data" / "new_keywords.json"
    output_path.parent.mkdir(exist_ok=True)

    # Load existing if present
    existing: dict[str, list[str]] = {}
    if output_path.exists():
        with open(output_path) as f:
            existing = json.load(f)

    # Merge
    for tag, keywords in new_entries.items():
        if tag in existing:
            existing[tag] = list(set(existing[tag]) | keywords)
        else:
            existing[tag] = list(keywords)

    with open(output_path, "w") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False, sort_keys=True)

    total_new = sum(len(v) for v in new_entries.values())
    logger.info("Saved %d new keyword mappings (%d tags) to %s", total_new, len(new_entries), output_path)


def merge_new_keywords_into_taxonomy() -> int:
    """
    Read new_keywords.json and merge into taxonomy.py's TAG_KEYWORDS.
    Call this after reviewing the new keywords.
    Returns the number of new keywords added.
    """
    from pipeline.taxonomy import TAG_KEYWORDS

    keywords_path = Path(__file__).parent.parent / "data" / "new_keywords.json"
    if not keywords_path.exists():
        logger.info("No new_keywords.json found")
        return 0

    with open(keywords_path) as f:
        new_keywords = json.load(f)

    added = 0
    for tag, de_keywords in new_keywords.items():
        if tag not in TAG_KEYWORDS:
            TAG_KEYWORDS[tag] = []
        for kw in de_keywords:
            if kw.lower() not in [k.lower() for k in TAG_KEYWORDS[tag]]:
                TAG_KEYWORDS[tag].append(kw.lower())
                added += 1

    # Clear the compiled patterns cache so new keywords take effect
    from pipeline.taxonomy import _COMPILED_TAG_PATTERNS
    _COMPILED_TAG_PATTERNS.clear()

    logger.info("Merged %d new keywords into TAG_KEYWORDS", added)
    return added
