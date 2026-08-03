"""
Categorizer: asks an LLM to assign category + tags to events that couldn't be
categorized from source metadata alone.

Model-agnostic (AGENTS.md rule 3): every call goes through a config-driven
gateway, defaulting to OpenRouter — the same route the embedder and the concierge
use, so one key covers the whole pipeline. Anthropic's native SDK stays available
as an alternate backend because it supports prompt caching on the system prompt,
which is the cost lever for a batched workload like this one.

Returns bilingual tags (EN + DE keywords) so that new German keywords
can be auto-expanded into the taxonomy keyword dictionary.

Uses batched requests (10 events/call) to minimize cost.

Env:
    CATEGORIZE_PROVIDER  openrouter | openai | anthropic   (default: openrouter)
    CATEGORIZE_MODEL     model id for the chosen provider
                         (default: anthropic/claude-haiku-4.5 via openrouter)
    OPENROUTER_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

_TIMEOUT = 120.0
MAX_TOKENS = 4096

DEFAULT_PROVIDER = "openrouter"
DEFAULT_MODELS = {
    "openrouter": "anthropic/claude-haiku-4.5",
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-haiku-4-5-20251001",
}
BASE_URLS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
}
KEY_ENV = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}

# Collect new keyword mappings discovered by the LLM
_new_keyword_mappings: list[dict[str, Any]] = []

CATEGORIES = [
    "music",
    "nightlife",
    "culture",
    "food",
    "markets",
    "workshops",
    "meetups",
    "outdoors",
    "family",
]

SUBCATEGORIES = {
    "music": [
        "jazz-blues",
        "electronic",
        "classical",
        "rock-pop",
        "hip-hop",
        "live-concert",
        "world-folk",
        "latin",
    ],
    "nightlife": ["club-night", "bar-event", "party", "comedy", "karaoke"],
    "culture": ["exhibition", "theater", "cinema", "reading", "gallery", "festival"],
    "food": ["brunch", "tasting", "pop-up", "dining-event", "food-market", "weekly-market"],
    "markets": ["flea-market", "design-market", "pop-up-fashion", "secondhand", "craft-market"],
    "workshops": ["creative-workshop", "language", "digital-skills", "dance-class", "craft"],
    "meetups": ["networking", "community", "tech-startup", "talk-panel", "activism"],
    "outdoors": ["walking-tour", "sports", "yoga-fitness", "bike-tour", "outdoor-cinema"],
    "family": ["kids-program", "family-event", "playground", "museum-for-kids"],
}

# Free-form subcategory values seen in the wild, mapped onto canonical tags.
# The UI filter (web/src/lib/types.ts SUBCATEGORIES) only knows canonical
# values — anything else is invisible to filtering, so it must never reach
# the DB.
SUBCATEGORY_SYNONYMS: dict[str, str] = {
    "jazz": "jazz-blues",
    "blues": "jazz-blues",
    "soul": "jazz-blues",
    "funk": "jazz-blues",
    "techno": "electronic",
    "house": "electronic",
    "dj set": "club-night",
    "dj-set": "club-night",
    "rock": "rock-pop",
    "pop": "rock-pop",
    "indie": "rock-pop",
    "punk": "rock-pop",
    "metal": "rock-pop",
    "hip hop": "hip-hop",
    "hiphop": "hip-hop",
    "rap": "hip-hop",
    "klassik": "classical",
    "concert": "live-concert",
    "konzert": "live-concert",
    "live performance": "live-concert",
    "live music": "live-concert",
    "acoustic": "live-concert",
    "world": "world-folk",
    "folk": "world-folk",
    "salsa": "latin",
    "after-work party": "party",
    "afterparty": "party",
    "bar party": "bar-event",
    "bar happy hour": "bar-event",
    "happy hour": "bar-event",
    "stand-up": "comedy",
    "standup": "comedy",
    "stand up": "comedy",
    "open mic": "comedy",
    "kabarett": "comedy",
    "art exhibition": "exhibition",
    "ausstellung": "exhibition",
    "museum": "exhibition",
    "experimental theater": "theater",
    "theatre": "theater",
    "kino": "cinema",
    "film": "cinema",
    "movie": "cinema",
    "lesung": "reading",
    "lecture": "talk-panel",
    "talk": "talk-panel",
    "panel": "talk-panel",
    "vortrag": "talk-panel",
    "meetup": "community",
    "networking dinner": "networking",
    "street food": "food-market",
    "streetfood": "food-market",
    "wochenmarkt": "weekly-market",
    "farmers market": "weekly-market",
    "flea market": "flea-market",
    "flohmarkt": "flea-market",
    "trödelmarkt": "flea-market",
    "vintage": "secondhand",
    "workshop": "creative-workshop",
    "kurs": "creative-workshop",
    "dance": "dance-class",
    "tanzkurs": "dance-class",
    "yoga": "yoga-fitness",
    "fitness": "yoga-fitness",
    "sport": "sports",
    "kids": "kids-program",
    "kinder": "kids-program",
    "kindertheater": "kids-program",
    "family": "family-event",
}

# Canonical subcategory → its parent category (for resolving mismatched pairs)
SUBCATEGORY_PARENT: dict[str, str] = {
    sub: cat for cat, subs in SUBCATEGORIES.items() for sub in subs
}


def normalize_subcategory(category: str | None, sub: str | None) -> str | None:
    """Map a free-form subcategory to a canonical tag valid for `category`.

    Returns None when no canonical tag fits — an unfilterable value is worse
    than an empty one.
    """
    if not sub:
        return None
    key = str(sub).lower().strip()
    key = SUBCATEGORY_SYNONYMS.get(key, key)
    if category and key in SUBCATEGORIES.get(category, []):
        return key
    return None


SYSTEM_PROMPT = """\
You are a Berlin event categorization assistant. Given event data, assign the best category, subcategory, and relevant English tags.

Categories (pick exactly one):
- music: concerts, live bands, jazz, classical, electronic, singer-songwriter
- nightlife: club nights, raves, DJ sets, parties, bar events, comedy, karaoke
- culture: exhibitions, theater, cinema, readings, galleries, festivals
- food: brunch, tastings, pop-up dinners, dining events, food markets, street food, farmers markets
- markets: flea markets, design markets, pop-up fashion, secondhand, craft markets (shopping-focused)
- workshops: creative workshops, language classes, digital skills, dance classes, craft
- meetups: networking, community events, tech/startup, talks/panels, activism
- outdoors: walking tours, sports, yoga/fitness, bike tours, outdoor cinema
- family: kids programs, family events, playgrounds, museums for kids

Subcategories per category:
- music: jazz-blues, electronic, classical, rock-pop, hip-hop, live-concert, world-folk, latin
- nightlife: club-night, bar-event, party, comedy, karaoke
- culture: exhibition, theater, cinema, reading, gallery, festival
- food: brunch, tasting, pop-up, dining-event, food-market, weekly-market
- markets: flea-market, design-market, pop-up-fashion, secondhand, craft-market
- workshops: creative-workshop, language, digital-skills, dance-class, craft
- meetups: networking, community, tech-startup, talk-panel, activism
- outdoors: walking-tour, sports, yoga-fitness, bike-tour, outdoor-cinema
- family: kids-program, family-event, playground, museum-for-kids

CATEGORIZATION RULES — follow these strictly:
0. subcategory MUST be exactly one of the values listed above for the chosen category (verbatim, hyphenated), or null. Never invent new subcategory values.
1. Categorize by the PRIMARY ACTIVITY the attendee goes for, not the venue type.
2. Live music (bands, concerts, singer-songwriter) at any venue → "music", even if it's at a bar.
3. DJ sets / techno / dance-focused events → "nightlife", even if there's live music too.
4. Shopping markets (flea, design, fashion, craft, secondhand) → "markets".
5. Art exhibitions, museum shows, gallery openings → "culture", even if there's a DJ or party after.
6. Street food markets, food festivals, farmers markets → "food" (the food IS the event).
7. Food events at restaurants, pop-ups, tastings → "food".
8. Comedy / stand-up / kabarett → "nightlife" (subcategory: comedy).
9. Yoga, fitness, sports → "outdoors" (not workshops).
10. If the title or venue contains "Flohmarkt", "Trödelmarkt", "Designmarkt" → "markets" (shopping). If it contains "Streetfood", "Wochenmarkt", "Bauernmarkt" → "food".
11. Events that are not real public events (police stations, administrative services) → quality_score: 0.0.
12. Events explicitly for children/kids/families → "family". Keywords: "für Kinder", "für Kids", "Kindertheater", "Puppentheater", "Krabbelgruppe", "Bilderbuchkino", "Vorlesestunde", "Familiencafé", "Kindercafé", "Familienkonzert", "Kinderkonzert", "Kinderfest". A children's theater show is "family", NOT "culture". A kids concert is "family", NOT "music".

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
                    _new_keyword_mappings.append(
                        {
                            "tag": en_tag,
                            "de": de_keywords if isinstance(de_keywords, list) else [de_keywords],
                        }
                    )
        elif isinstance(tag_entry, str):
            en_tags.append(tag_entry)
    return en_tags


def _apply_result(event: dict[str, Any], result: dict[str, Any]) -> None:
    """Apply a single LLM result to an event dict (in-place)."""
    if result.get("category") in CATEGORIES:
        event["category"] = result["category"]
        # Only canonical subcategories reach the DB — the UI filter can't see
        # anything else. Synonyms are normalized, the rest is dropped.
        sub = normalize_subcategory(event["category"], result.get("subcategory"))
        if sub:
            event["subcategory"] = sub
        elif normalize_subcategory(event["category"], event.get("subcategory")) is None:
            event["subcategory"] = None

    raw_tags = result.get("tags") or []
    en_tags = _parse_tags(raw_tags)
    event["tags"] = en_tags or event.get("tags") or []
    event["quality_score"] = result.get("quality_score")


# ── Model gateway ─────────────────────────────────────────────────────────────


class OpenAICompatChat:
    """Any /v1/chat/completions endpoint speaking the OpenAI schema."""

    def __init__(self, provider: str, model: str):
        self.provider = provider
        self.model = model
        self._url = BASE_URLS[provider].rstrip("/") + "/chat/completions"
        self._key = os.environ.get(KEY_ENV[provider], "")

    def complete(self, system: str, user: str) -> str:
        resp = httpx.post(
            self._url,
            headers={"Authorization": f"Bearer {self._key}"},
            json={
                "model": self.model,
                "max_tokens": MAX_TOKENS,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


class AnthropicChat:
    """Native Anthropic SDK — kept for its system-prompt caching, which matters
    when the same 2k-token prompt precedes every batch."""

    def __init__(self, model: str):
        self.provider = "anthropic"
        self.model = model
        self._key = os.environ.get(KEY_ENV["anthropic"], "")

    def complete(self, system: str, user: str) -> str:
        import anthropic  # imported lazily: only this backend needs the SDK

        client = anthropic.Anthropic(api_key=self._key)
        message = client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text


def has_key(provider: str) -> bool:
    return bool(os.environ.get(KEY_ENV.get(provider, ""), ""))


def get_chat_client():
    """Resolve the configured backend, falling back to any provider whose key IS
    present. A stale key on the configured provider should degrade to a working
    one rather than silently drop categorisation for a whole nightly run."""
    name = (os.environ.get("CATEGORIZE_PROVIDER") or DEFAULT_PROVIDER).lower()
    if name not in DEFAULT_MODELS:
        logger.warning("Unknown CATEGORIZE_PROVIDER %r — using %s", name, DEFAULT_PROVIDER)
        name = DEFAULT_PROVIDER
    if not has_key(name):
        alternate = next((p for p in DEFAULT_MODELS if has_key(p)), None)
        if alternate is None:
            return None
        logger.warning("No %s — falling back to %s for categorization", KEY_ENV[name], alternate)
        name = alternate
    model = os.environ.get("CATEGORIZE_MODEL") or DEFAULT_MODELS[name]
    if name == "anthropic":
        return AnthropicChat(model)
    return OpenAICompatChat(name, model)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _categorize_batch_call(client, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Send a batch of events to the model and return parsed results."""
    payloads = [_make_event_payload(e) for e in events]
    user_content = json.dumps(payloads, ensure_ascii=False)

    raw = client.complete(SYSTEM_PROMPT, user_content).strip()
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
    if (
        event.get("category")
        and event.get("subcategory")
        and event.get("tags")
        and event.get("quality_score") is not None
    ):
        return event

    client = get_chat_client()
    if client is None:
        logger.warning("No LLM API key — skipping categorization for '%s'", event.get("title"))
        return event

    try:
        results = _categorize_batch_call(client, [event])
        if results:
            _apply_result(event, results[0])
    except Exception as e:
        logger.error("Categorization failed for '%s': %s", event.get("title"), e)

    return event


def categorize_batch(events: list[dict[str, Any]], max_llm: int = 2500) -> list[dict[str, Any]]:
    """Categorize a list of events. Skips already-categorized ones."""
    # Deterministic beats model: an explicit source tag ("Comedy") or a hard title
    # signal decides BEFORE the LLM sees it — the "Meanwhile in Berlin" case, where
    # the LLM filed a Comedy-tagged stand-up show under culture despite prompt rules.
    for e in events:
        if e.get("category") == "nightlife" and e.get("subcategory") == "comedy":
            continue
        signal_text = " ".join(
            [
                str(e.get("title") or ""),
                " ".join(str(t) for t in (e.get("source_tags") or e.get("tags") or [])),
            ]
        ).lower()
        if re.search(r"\bcomedy\b|\bstand.?up\b|\bkabarett\b|\bopen mic\b", signal_text):
            e["category"] = "nightlife"
            e["subcategory"] = "comedy"

    needs_categorization = [
        e for e in events if not (e.get("category") and e.get("subcategory") and e.get("tags"))
    ]
    already_done = [
        e for e in events if e.get("category") and e.get("subcategory") and e.get("tags")
    ]

    logger.info(
        "Categorizing %d events (%d already done)", len(needs_categorization), len(already_done)
    )

    if len(needs_categorization) > max_llm:
        logger.info(
            "Too many to categorize (%d > %d). Run categorizer separately or increase max_llm.",
            len(needs_categorization),
            max_llm,
        )
        return events

    if not needs_categorization:
        return events

    client = get_chat_client()
    if client is None:
        logger.warning("No LLM API key — skipping LLM categorization")
        return events

    logger.info("Categorizing via %s / %s", client.provider, client.model)
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
        f.write("\n")  # the repo's end-of-file-fixer hook rewrites the file otherwise

    total_new = sum(len(v) for v in new_entries.values())
    logger.info(
        "Saved %d new keyword mappings (%d tags) to %s", total_new, len(new_entries), output_path
    )


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
