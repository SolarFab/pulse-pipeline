"""Swappable event embedder (preference-feed task 1.2).

One canonical embed-text builder + an OpenAI-compatible embeddings client.
Default gateway is OpenRouter — one key, many embedding models (OpenAI, Google,
Qwen, Cohere …) — keeping every model call in Pulse behind one config-driven
gateway (see AGENTS.md: model-agnostic). Direct OpenAI/Gemini remain available
as alternate bases.

Env:
    EMBED_PROVIDER   openrouter | openai | gemini      (default: openrouter)
    EMBED_MODEL      model id for the chosen provider
                     (default: openai/text-embedding-3-small via openrouter)
    EMBED_DIM        optional output dimension; omit to use the model's native size
    OPENROUTER_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY
"""

from __future__ import annotations

import hashlib
import os

import httpx

_TIMEOUT = 60.0
_BATCH_SIZE = 100

DEFAULT_PROVIDER = "openrouter"
DEFAULT_MODELS = {
    "openrouter": "openai/text-embedding-3-small",
    "openai": "text-embedding-3-small",
    "gemini": "text-embedding-004",
}
KEY_ENV = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
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


# ── Client ────────────────────────────────────────────────────────────────────


class OpenAICompatEmbedder:
    """Any /v1/embeddings endpoint speaking the OpenAI schema (OpenRouter, OpenAI)."""

    def __init__(self, provider: str, base_url: str, model: str, dim: int | None):
        self.provider = provider
        self.model = model
        self.dim = dim
        self.total_tokens = 0  # accumulated across calls — cost/latency evaluation
        self.total_seconds = 0.0
        self._url = base_url.rstrip("/") + "/embeddings"
        self._key = os.environ.get(KEY_ENV[provider], "")

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        import time

        out: list[list[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            chunk = texts[i : i + _BATCH_SIZE]
            payload: dict = {"model": self.model, "input": chunk}
            if self.dim:  # only models that support shortening (e.g. text-embedding-3-*)
                payload["dimensions"] = self.dim
            t0 = time.time()
            resp = httpx.post(
                self._url,
                headers={"Authorization": f"Bearer {self._key}"},
                json=payload,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            body = resp.json()
            self.total_seconds += time.time() - t0
            self.total_tokens += (body.get("usage") or {}).get("total_tokens", 0)
            data = sorted(body["data"], key=lambda d: d["index"])
            out.extend(d["embedding"] for d in data)
        return out


class GeminiEmbedder:
    """Direct Google endpoint (fallback if not routing through OpenRouter)."""

    provider = "gemini"

    def __init__(self, model: str = DEFAULT_MODELS["gemini"], dim: int | None = None):
        self.model = model
        self.dim = dim
        self._key = os.environ.get(KEY_ENV["gemini"], "")

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            chunk = texts[i : i + _BATCH_SIZE]
            req = [
                {"model": f"models/{self.model}", "content": {"parts": [{"text": t}]}}
                for t in chunk
            ]
            if self.dim:
                for r in req:
                    r["outputDimensionality"] = self.dim
            resp = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:batchEmbedContents",
                params={"key": self._key},
                json={"requests": req},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            out.extend(e["values"] for e in resp.json()["embeddings"])
        return out


def get_embedder(provider: str | None = None, model: str | None = None):
    """Build the configured embedder. Config only — never hardcode a provider at call sites."""
    name = (provider or os.environ.get("EMBED_PROVIDER") or DEFAULT_PROVIDER).lower()
    if name not in KEY_ENV:
        raise ValueError(f"unknown EMBED_PROVIDER {name!r}; expected one of {sorted(KEY_ENV)}")
    model = model or os.environ.get("EMBED_MODEL") or DEFAULT_MODELS[name]
    dim_env = os.environ.get("EMBED_DIM")
    dim = int(dim_env) if dim_env else None
    if name == "gemini":
        return GeminiEmbedder(model=model, dim=dim)
    base = {
        "openrouter": "https://openrouter.ai/api/v1",
        "openai": "https://api.openai.com/v1",
    }[name]
    return OpenAICompatEmbedder(provider=name, base_url=base, model=model, dim=dim)


def has_key(provider: str) -> bool:
    return bool(os.environ.get(KEY_ENV[provider]))
