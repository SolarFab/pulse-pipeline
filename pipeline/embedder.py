"""Swappable event embedder (preference-feed task 1.2).

One canonical embed-text builder + provider backends selected by env config.
Providers are called via raw REST (httpx) — no provider SDKs, so swapping models
is config, not code (see AGENTS.md: model-agnostic).

Env:
    EMBED_PROVIDER   openai | gemini            (default: openai)
    EMBED_MODEL      provider model id          (defaults per provider)
    EMBED_DIM        output dimension           (default: 768 — both providers support it)
    OPENAI_API_KEY / GEMINI_API_KEY
"""

from __future__ import annotations

import hashlib
import os
from typing import Protocol

import httpx

_TIMEOUT = 30.0
_BATCH_SIZE = 100

DEFAULT_DIM = 768
DEFAULT_MODELS = {
    "openai": "text-embedding-3-small",
    "gemini": "text-embedding-004",
}


# ── Canonical embed text ──────────────────────────────────────────────────────
# Stable by design: the hash of this text decides whether an event is re-embedded,
# so field order and formatting must never change casually.

def build_embed_text(event: dict) -> str:
    """title + description + category/subcategory + tags, in a fixed layout."""
    parts = [
        (event.get("title") or "").strip(),
        (event.get("description") or "").strip()[:1500],
        f"category: {event.get('category') or ''}/{event.get('subcategory') or ''}",
    ]
    tags = event.get("tags") or []
    if tags:
        parts.append("tags: " + ", ".join(sorted(tags)[:15]))
    return "\n".join(p for p in parts if p)


def embed_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── Providers ─────────────────────────────────────────────────────────────────

class Embedder(Protocol):
    provider: str
    model: str
    dim: int

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    provider = "openai"

    def __init__(self, model: str = DEFAULT_MODELS["openai"], dim: int = DEFAULT_DIM):
        self.model = model
        self.dim = dim
        self._key = os.environ.get("OPENAI_API_KEY", "")

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            chunk = texts[i : i + _BATCH_SIZE]
            resp = httpx.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self._key}"},
                json={"model": self.model, "input": chunk, "dimensions": self.dim},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            out.extend(d["embedding"] for d in data)
        return out


class GeminiEmbedder:
    provider = "gemini"

    def __init__(self, model: str = DEFAULT_MODELS["gemini"], dim: int = DEFAULT_DIM):
        self.model = model
        self.dim = dim
        self._key = os.environ.get("GEMINI_API_KEY", "")

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            chunk = texts[i : i + _BATCH_SIZE]
            resp = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:batchEmbedContents",
                params={"key": self._key},
                json={
                    "requests": [
                        {
                            "model": f"models/{self.model}",
                            "content": {"parts": [{"text": t}]},
                            "outputDimensionality": self.dim,
                        }
                        for t in chunk
                    ]
                },
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            out.extend(e["values"] for e in resp.json()["embeddings"])
        return out


_PROVIDERS = {"openai": OpenAIEmbedder, "gemini": GeminiEmbedder}


def get_embedder(provider: str | None = None) -> Embedder:
    """Build the configured embedder. Config only — never hardcode a provider at call sites."""
    name = (provider or os.environ.get("EMBED_PROVIDER") or "openai").lower()
    if name not in _PROVIDERS:
        raise ValueError(f"unknown EMBED_PROVIDER {name!r}; expected one of {sorted(_PROVIDERS)}")
    model = os.environ.get("EMBED_MODEL") or DEFAULT_MODELS[name]
    dim = int(os.environ.get("EMBED_DIM") or DEFAULT_DIM)
    return _PROVIDERS[name](model=model, dim=dim)


def has_key(provider: str) -> bool:
    env = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}[provider]
    return bool(os.environ.get(env))
