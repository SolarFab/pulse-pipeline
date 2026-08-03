"""Categorizer model-gateway tests — no network, no DB.

Covers provider selection only; the prompt rules are exercised by the golden set.
"""

import pytest

from pipeline.categorizer import (
    AnthropicChat,
    OpenAICompatChat,
    get_chat_client,
)

ALL_KEYS = ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in (*ALL_KEYS, "CATEGORIZE_PROVIDER", "CATEGORIZE_MODEL"):
        monkeypatch.delenv(key, raising=False)


def test_defaults_to_openrouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    client = get_chat_client()
    assert isinstance(client, OpenAICompatChat)
    assert client.provider == "openrouter"
    assert "openrouter.ai" in client._url


def test_provider_and_model_are_configurable(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("CATEGORIZE_PROVIDER", "openai")
    monkeypatch.setenv("CATEGORIZE_MODEL", "gpt-4.1-nano")
    client = get_chat_client()
    assert client.provider == "openai" and client.model == "gpt-4.1-nano"


def test_anthropic_backend_selectable(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("CATEGORIZE_PROVIDER", "anthropic")
    assert isinstance(get_chat_client(), AnthropicChat)


def test_falls_back_to_a_provider_whose_key_exists(monkeypatch):
    """A stale key on the configured provider must not silently drop
    categorization for an entire nightly run — this is the failure that
    motivated the refactor."""
    monkeypatch.setenv("CATEGORIZE_PROVIDER", "anthropic")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    client = get_chat_client()
    assert client.provider == "openrouter"


def test_unknown_provider_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("CATEGORIZE_PROVIDER", "hal9000")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    assert get_chat_client().provider == "openrouter"


def test_no_keys_returns_none_rather_than_raising(monkeypatch):
    assert get_chat_client() is None
