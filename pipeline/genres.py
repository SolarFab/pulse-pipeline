"""Canonical genre vocabulary + detection (genre-dimension §1.2, §2.3).

Genre is a dimension of its own: multi-valued, flat, curated — the industry
consensus (MusicBrainz whitelist, Discogs genre/style, RA's 70 promoter tags)
and the opposite of `subcategory`, which is single-valued and loses genre to
format every time.

Two rules keep this vocabulary honest:
  1. NO format words. `club`, `party`, `concert`, `live music`, `festival` are
     formats, not genres — RA's own list has "Club" and NOCTAVA's has "Live
     Music"; both are the mistake we're escaping.
  2. Detection is conservative. No signal -> no tag (same discipline as
     pipeline/facets.py). A missing genre costs recall; a wrong one poisons a
     filter users trust.

Seeded into the `taxonomy` table by scripts/seed_genres.py; the DB is the
runtime source of truth (pipeline + web both read it there).
"""

from __future__ import annotations

import re

# ── Umbrella groups (UI roll-up; a genre always belongs to exactly one) ───────
GENRE_GROUPS: dict[str, tuple[str, str]] = {
    "electronic": ("Elektronisch", "Electronic"),
    "bass": ("Bass", "Bass"),
    "hard": ("Hart & Industrial", "Hard & Industrial"),
    "ambient": ("Ambient & Downtempo", "Ambient & Downtempo"),
    "hip-hop": ("Hip-Hop", "Hip-Hop"),
    "rnb-soul": ("R&B & Soul", "R&B & Soul"),
    "afro": ("Afro", "Afro"),
    "latin": ("Latin", "Latin"),
    "reggae": ("Reggae & Dancehall", "Reggae & Dancehall"),
    "disco": ("Disco & Funk", "Disco & Funk"),
    "jazz": ("Jazz & Blues", "Jazz & Blues"),
    "classical": ("Klassik", "Classical"),
    "rock-pop": ("Rock & Pop", "Rock & Pop"),
    "world-folk": ("World & Folk", "World & Folk"),
    "experimental": ("Experimentell", "Experimental"),
}

# slug -> (group, label_de, label_en, aliases, keywords)
# `aliases`  — source vocabulary values mapped onto this slug (lowercased match).
# `keywords` — extra regex fragments for the text detector; empty tuple means
#              "detect by the label only"; None means "never detect from text"
#              (too ambiguous in German prose — source metadata only).
_G: dict[str, tuple[str, str, str, tuple[str, ...], tuple[str, ...] | None]] = {
    # ── electronic ───────────────────────────────────────────────────────────
    "techno": ("electronic", "Techno", "Techno", (), ()),
    "minimal-techno": ("electronic", "Minimal Techno", "Minimal Techno", (), ()),
    "dub-techno": ("electronic", "Dub Techno", "Dub Techno", (), ()),
    "hard-techno": ("electronic", "Hard Techno", "Hard Techno", (), ()),
    "house": ("electronic", "House", "House", (), ()),
    "tech-house": ("electronic", "Tech House", "Tech House", (), ()),
    "deep-house": ("electronic", "Deep House", "Deep House", (), ()),
    "progressive-house": ("electronic", "Progressive House", "Progressive House", (), ()),
    "afro-house": ("electronic", "Afro House", "Afro House", (), ()),
    "afro-tech": ("electronic", "Afro Tech", "Afro Tech", (), ()),
    "minimal": ("electronic", "Minimal", "Minimal", (), None),
    "acid": ("electronic", "Acid", "Acid", (), ()),
    "trance": ("electronic", "Trance", "Trance", (), ()),
    "psytrance": ("electronic", "Psytrance", "Psytrance", ("psy trance",), ()),
    "electro": ("electronic", "Electro", "Electro", (), None),
    "electronica": ("electronic", "Electronica", "Electronica", (), ()),
    "idm": ("electronic", "IDM", "IDM", (), None),
    "ghetto-tech": ("electronic", "Ghetto Tech", "Ghetto Tech", (), ()),
    "hard-drum": ("electronic", "Hard Drum", "Hard Drum", (), ()),
    "singeli": ("electronic", "Singeli", "Singeli", (), ()),
    "gqom": ("electronic", "Gqom", "Gqom", (), ()),
    "electronic": (
        "electronic",
        "Elektronisch",
        "Electronic",
        (
            "edm",
            "edm / electronic",
            "elektronisch",
            "elektronische musik",
            "dj/dance",
            "electronic dance music",
        ),
        ("elektro(nisch)?e? musik",),
    ),
    # ── bass ─────────────────────────────────────────────────────────────────
    "drum-and-bass": (
        "bass",
        "Drum & Bass",
        "Drum & Bass",
        ("dnb", "d&b", "drum n bass", "drum'n'bass"),
        (r"drum\s*(&|and|'?n'?)\s*bass",),
    ),
    "jungle": ("bass", "Jungle", "Jungle", (), None),
    "dubstep": ("bass", "Dubstep", "Dubstep", (), ()),
    "bass": ("bass", "Bass", "Bass", (), ("bass music",)),
    "garage": ("bass", "Garage", "Garage", ("uk garage",), ("uk garage",)),
    "uk-funky": ("bass", "UK Funky", "UK Funky", (), ()),
    "footwork": ("bass", "Footwork", "Footwork", (), ()),
    "grime": ("bass", "Grime", "Grime", (), ()),
    "breakbeat": ("bass", "Breakbeat", "Breakbeat", (), ()),
    "breakcore": ("bass", "Breakcore", "Breakcore", (), ()),
    # ── hard / industrial ────────────────────────────────────────────────────
    "hardcore": ("hard", "Hardcore", "Hardcore", (), ()),
    "gabber": ("hard", "Gabber", "Gabber", (), ()),
    "industrial": ("hard", "Industrial", "Industrial", (), None),
    "ebm": ("hard", "EBM", "EBM", (), None),
    "noise": ("hard", "Noise", "Noise", (), None),
    # ── ambient / downtempo ──────────────────────────────────────────────────
    "ambient": ("ambient", "Ambient", "Ambient", (), ()),
    "drone": ("ambient", "Drone", "Drone", (), None),
    "downtempo": ("ambient", "Downtempo", "Downtempo", (), ()),
    "dub": ("ambient", "Dub", "Dub", (), None),
    "vaporwave": ("ambient", "Vaporwave", "Vaporwave", (), ()),
    "trip-hop": ("ambient", "Trip-Hop", "Trip-Hop", ("triphop",), (r"trip[\s-]?hop",)),
    # ── hip-hop ──────────────────────────────────────────────────────────────
    "hip-hop": (
        "hip-hop",
        "Hip-Hop",
        "Hip-Hop",
        (
            "hip hop",
            "hiphop",
            "hip hop / rap",
            "hip-hop/rap",
            "hip hop/rap",
            "rap",
            "hip-hop / rap",
        ),
        (
            r"hip[\s-]?hop",
            r"\brap[\s-]?(musik|music|show|battle|night|konzert)\b",
            r"\bdeutschrap\b",
            r"\bboom[\s-]?bap\b",
            r"\bfreestyle[\s-]?(session|battle|cypher)\b",
        ),
    ),
    "drill": ("hip-hop", "Drill", "Drill", (), ()),
    "trap": ("hip-hop", "Trap", "Trap", (), (r"\btrap\b(?!\w)",)),
    # ── R&B / soul ───────────────────────────────────────────────────────────
    "r-and-b": (
        "rnb-soul",
        "R&B",
        "R&B",
        ("r&b", "rnb", "r'n'b", "r&b/soul", "rhythm and blues"),
        (r"\br&b\b", r"\brnb\b"),
    ),
    "soul": ("rnb-soul", "Soul", "Soul", ("funk / soul", "funk/soul"), ()),
    "funk": ("rnb-soul", "Funk", "Funk", (), (r"\bfunk\b(?!tion)",)),
    "neo-soul": ("rnb-soul", "Neo Soul", "Neo Soul", (), ()),
    # ── afro ─────────────────────────────────────────────────────────────────
    "afrobeats": ("afro", "Afrobeats", "Afrobeats", ("afro beats",), ()),
    "afrobeat": ("afro", "Afrobeat", "Afrobeat", (), ()),
    "amapiano": ("afro", "Amapiano", "Amapiano", (), ()),
    "kuduro": ("afro", "Kuduro", "Kuduro", (), ()),
    "kwaito": ("afro", "Kwaito", "Kwaito", (), ()),
    # ── latin ────────────────────────────────────────────────────────────────
    "reggaeton": ("latin", "Reggaeton", "Reggaeton", ("reggaetón",), ("reggaet[oó]n",)),
    "dembow": ("latin", "Dembow", "Dembow", (), ()),
    "baile-funk": ("latin", "Baile Funk", "Baile Funk", (), ()),
    "rio-funk": ("latin", "Rio Funk", "Rio Funk", (), ()),
    "latin-bass": ("latin", "Latin Bass", "Latin Bass", (), ()),
    "guaracha": ("latin", "Guaracha", "Guaracha", (), ()),
    "neo-perreo": ("latin", "Neo Perreo", "Neo Perreo", (), ()),
    "salsa": ("latin", "Salsa", "Salsa", (), ()),
    "cumbia": ("latin", "Cumbia", "Cumbia", (), ()),
    "latin": (
        "latin",
        "Latin",
        "Latin",
        ("latino", "latin music"),
        ("latin[\\s-]?(musik|music|night|party)",),
    ),
    # ── reggae / dancehall ───────────────────────────────────────────────────
    "dancehall": ("reggae", "Dancehall", "Dancehall", (), ()),
    "reggae": ("reggae", "Reggae", "Reggae", (), ()),
    # ── disco / funk ─────────────────────────────────────────────────────────
    "disco": ("disco", "Disco", "Disco", (), (r"\bdisco\b(?!thek)",)),
    "italo-disco": ("disco", "Italo Disco", "Italo Disco", (), ()),
    "balearic": ("disco", "Balearic", "Balearic", (), ()),
    "broken-beat": ("disco", "Broken Beat", "Broken Beat", (), ()),
    "ballroom": ("disco", "Ballroom", "Ballroom", (), None),
    # ── jazz / blues ─────────────────────────────────────────────────────────
    "jazz": (
        "jazz",
        "Jazz",
        "Jazz",
        ("blues & jazz", "jazz & blues", "modern jazz", "vocal jazz"),
        (),
    ),
    "blues": ("jazz", "Blues", "Blues", (), ()),
    "swing": ("jazz", "Swing", "Swing", (), ()),
    # ── classical ────────────────────────────────────────────────────────────
    "classical": (
        "classical",
        "Klassik",
        "Classical",
        ("klassik", "klassische musik", "klassische konzerte"),
        (r"\bklassik\b", r"klassische[rn]? (musik|konzert)"),
    ),
    "opera": ("classical", "Oper", "Opera", ("oper", "operette"), (r"\boper\b", r"\boperette\b")),
    "contemporary-classical": (
        "classical",
        "Neue Musik",
        "Contemporary Classical",
        ("neue musik",),
        (r"\bneue musik\b",),
    ),
    # ── rock / pop ───────────────────────────────────────────────────────────
    "rock": ("rock-pop", "Rock", "Rock", (), (r"\brock\b(?!ab|en)",)),
    "pop": ("rock-pop", "Pop", "Pop", ("top 40",), (r"\bpop\b(?![\s-]?up)",)),
    "indie": ("rock-pop", "Indie", "Indie", ("indie pop", "indie rock"), ()),
    "punk": ("rock-pop", "Punk", "Punk", ("punk/hardcore",), ()),
    "post-punk": ("rock-pop", "Post-Punk", "Post-Punk", (), (r"post[\s-]?punk",)),
    "metal": ("rock-pop", "Metal", "Metal", ("hard & heavy", "heavy metal"), ()),
    "new-wave": ("rock-pop", "New Wave", "New Wave", (), ()),
    "krautrock": ("rock-pop", "Krautrock", "Krautrock", (), ()),
    "singer-songwriter": (
        "rock-pop",
        "Singer-Songwriter",
        "Singer-Songwriter",
        ("singer/songwriter",),
        (r"singer[\s-]?songwriter",),
    ),
    # ── world / folk ─────────────────────────────────────────────────────────
    "folk": ("world-folk", "Folk", "Folk", ("country & folk", "americana", "bluegrass"), ()),
    "world": (
        "world-folk",
        "Weltmusik",
        "World",
        ("world music", "weltmusik", "cultural"),
        (r"\bweltmusik\b", r"\bworld music\b"),
    ),
    "schlager": ("world-folk", "Schlager", "Schlager", ("schlager & volksmusik",), ()),
    "chanson": ("world-folk", "Chanson", "Chanson", ("lieder & chanson",), ()),
    "balkan": ("world-folk", "Balkan", "Balkan", (), (r"balkan[\s-]?(beats|brass|musik|music)",)),
    "klezmer": ("world-folk", "Klezmer", "Klezmer", (), ()),
    # ── experimental ─────────────────────────────────────────────────────────
    "experimental": (
        "experimental",
        "Experimentell",
        "Experimental",
        ("experimentell",),
        (r"experimentell", r"experimental (music|musik|sound)"),
    ),
}

# Format words that must never enter the genre vocabulary (rule 1). Kept as an
# explicit list so the seed test can assert it.
FORMAT_WORDS = frozenset(
    {
        "club",
        "party",
        "concert",
        "konzert",
        "live-music",
        "live-concert",
        "festival",
        "dj-set",
        "rave",
        "open-air",
        "gig",
        "show",
        "performance",
    }
)

GENRE_SLUGS: frozenset[str] = frozenset(_G)


def genre_rows() -> list[dict]:
    """Taxonomy rows for the genre dimension (groups first, then genres)."""
    rows: list[dict] = []
    for order, (group, (de, en)) in enumerate(GENRE_GROUPS.items()):
        rows.append(
            {
                "kind": "genre-group",
                "category_slug": group,
                "subcategory_slug": None,
                "label_de": de,
                "label_en": en,
                "parent": None,
                "aliases": [],
                "sort_order": order * 100,
                "is_active": True,
            }
        )
    group_order = {g: i for i, g in enumerate(GENRE_GROUPS)}
    for i, (slug, (group, de, en, aliases, _kw)) in enumerate(sorted(_G.items())):
        rows.append(
            {
                "kind": "genre",
                "category_slug": slug,
                "subcategory_slug": None,
                "label_de": de,
                "label_en": en,
                "parent": group,
                "aliases": sorted(
                    {a.lower() for a in aliases} | {slug.replace("-", " "), en.lower()}
                ),
                "sort_order": group_order[group] * 100 + i,
                "is_active": True,
            }
        )
    return rows


def alias_map() -> dict[str, str]:
    """Lowercased source value -> canonical genre slug."""
    out: dict[str, str] = {}
    for row in genre_rows():
        if row["kind"] != "genre":
            continue
        for alias in row["aliases"]:
            out.setdefault(alias, row["category_slug"])
        out[row["category_slug"]] = row["category_slug"]
    return out


def _pattern(slug: str, label_en: str, keywords: tuple[str, ...] | None) -> re.Pattern | None:
    if keywords is None:
        return None
    frags = list(keywords) or [re.escape(label_en).replace(r"\ ", r"[\s-]?")]
    return re.compile(r"(?<!\w)(?:" + "|".join(frags) + r")(?!\w)", re.IGNORECASE)


_PATTERNS: list[tuple[str, re.Pattern]] = [
    (slug, pat)
    for slug, (_grp, _de, en, _al, kw) in _G.items()
    if (pat := _pattern(slug, en, kw)) is not None
]


# Text detection only runs where music is plausibly the point of the event. A
# senior meetup whose description lists "Lesungen, Reiseberichte, klassische
# Musik" among afternoon activities is a true keyword match and a false genre
# claim — the words appear in a menu, not as the billing. Source-asserted
# genres (promoter tags, Eventbrite subcategory) are explicit and always apply.
TEXT_DETECT_CATEGORIES = frozenset({"music", "nightlife", "culture"})


def detect_genres(event: dict) -> list[str]:
    """Canonical genres detectable from an event's own text + source tags.

    Conservative by construction: only whitelist slugs, only explicit matches,
    no inference. Returns [] when nothing matches — absence beats a wrong tag.
    """
    aliases = alias_map()
    found: list[str] = []

    for raw in event.get("source_tags") or []:
        slug = aliases.get(str(raw).strip().lower())
        if slug and slug not in found:
            found.append(slug)

    if event.get("category") not in TEXT_DETECT_CATEGORIES:
        return found

    text = " ".join(str(event.get(f) or "") for f in ("title", "description"))
    if text.strip():
        for slug, pattern in _PATTERNS:
            if slug not in found and pattern.search(text):
                found.append(slug)
    return found


def canonicalize(values: list[str] | None) -> list[str]:
    """Map arbitrary source genre values onto canonical slugs (unknowns dropped)."""
    aliases = alias_map()
    out: list[str] = []
    for v in values or []:
        slug = aliases.get(str(v).strip().lower())
        if slug and slug not in out:
            out.append(slug)
    return out


def merge_genres(event: dict) -> list[str]:
    """Canonical genres for an event: detected values unioned with stored ones.

    Writes the dedicated `genres` column, NOT `tags`. Keeping the dimension in
    its own column is load-bearing: `tags` carries years of free-text
    categorizer output that collides with genre names — an audit found 955
    events tagged `singer-songwriter` (library senior meetups), 241 `classical`
    (after-school gaming), and 604 `electronic` (the old RA hardcode, incl.
    salsa classes). Filtering genre over `tags` would surface all of it. Only
    the deterministic waterfall writes here; the LLM free-tagger never does.

    Idempotent: re-running adds nothing new, so this can run on every scrape
    pass and heal rows stored before the genre dimension existed.
    """
    genres = [g for g in (event.get("genres") or []) if g in GENRE_SLUGS]
    for slug in detect_genres(event):
        if slug not in genres:
            genres.append(slug)
    return genres
