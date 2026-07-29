"""Embedder unit tests — no network, no DB."""

import pytest

from pipeline.embedder import (
    DEFAULT_DIM,
    build_embed_text,
    embed_text_hash,
    get_embedder,
)

EVENT = {
    "title": "Jazz Night at A-Trane",
    "description": "Live bebop and swing with local trio.",
    "category": "music",
    "subcategory": "jazz-blues",
    "tags": ["jazz", "live", "bebop"],
}


def test_embed_text_is_stable_and_ordered():
    text = build_embed_text(EVENT)
    assert text == build_embed_text(dict(EVENT))  # same input → identical text
    assert text.index("Jazz Night") < text.index("category: music/jazz-blues")
    assert "tags: bebop, jazz, live" in text  # tags sorted → order-insensitive


def test_hash_changes_when_embed_relevant_field_changes():
    h1 = embed_text_hash(build_embed_text(EVENT))
    recategorized = {**EVENT, "category": "nightlife"}
    assert embed_text_hash(build_embed_text(recategorized)) != h1
    # non-embed fields (e.g. price) must NOT change the hash
    assert embed_text_hash(build_embed_text({**EVENT, "price": "20€"})) == h1


def test_missing_fields_do_not_crash():
    assert build_embed_text({"title": "X"}).startswith("X")
    assert build_embed_text({}) == "category: /"


def test_provider_selection_from_env(monkeypatch):
    monkeypatch.setenv("EMBED_PROVIDER", "gemini")
    emb = get_embedder()
    assert emb.provider == "gemini" and emb.dim == DEFAULT_DIM

    monkeypatch.setenv("EMBED_PROVIDER", "openai")
    monkeypatch.setenv("EMBED_DIM", "1536")
    assert get_embedder().dim == 1536


def test_unknown_provider_rejected(monkeypatch):
    monkeypatch.setenv("EMBED_PROVIDER", "acme")
    with pytest.raises(ValueError, match="acme"):
        get_embedder()
