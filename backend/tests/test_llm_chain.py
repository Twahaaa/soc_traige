"""Tests for the provider-agnostic LLM wrapper.

These tests cover the fallback contract using fake clients — no live API calls
or real provider SDKs are exercised.
"""

from __future__ import annotations

import os

import pytest

from triage.llm.base import LLMClient, ProviderError
from triage.llm.chain import LLMChain
from triage.llm.factory import build_chain
from triage.llm.providers import (
    OLLAMA_NAME,
    build_groq,
    build_ollama,
    build_opencode_go,
    build_openrouter,
)


def _fake_client(
    name: str,
    *,
    content: str | None = None,
    fail: bool = False,
    available: bool = True,
) -> LLMClient:
    """Build an LLMClient whose invoke() behaviour is fully controlled."""

    class _FakeModel:
        def __init__(self) -> None:
            self.invoke_count = 0

        def invoke(self, messages):  # noqa: ANN001 - matches langchain signature loosely
            self.invoke_count += 1
            if fail:
                raise RuntimeError("fake failure")
            return type("Resp", (), {"content": content})()

    model = _FakeModel() if available else None
    client = LLMClient(name, model, available=available)
    client._model = model  # type: ignore[attr-defined] - test hook to inspect invoke_count
    return client


# ---------------------------------------------------------------------------
# Chain behaviour
# ---------------------------------------------------------------------------


def test_chain_returns_first_success():
    a = _fake_client("a", fail=True)
    b = _fake_client("b", content="OK")
    chain = LLMChain([a, b], retries=0)

    assert chain.invoke("prompt") == "OK"
    assert a._model.invoke_count == 1  # one try, then moved on
    assert b._model.invoke_count == 1


def test_chain_skips_unavailable():
    a = _fake_client("a", available=False)
    b = _fake_client("b", content="OK")
    chain = LLMChain([a, b], retries=0)

    assert chain.invoke("prompt") == "OK"
    assert a._model is None
    assert b._model.invoke_count == 1


def test_chain_retries_per_provider():
    a = _fake_client("a", fail=True)
    chain = LLMChain([a], retries=2)

    assert chain.invoke("prompt") is None
    assert a._model.invoke_count == 3  # 1 initial + 2 retries


def test_chain_all_fail_returns_none():
    a = _fake_client("a", fail=True)
    b = _fake_client("b", fail=True)
    chain = LLMChain([a, b], retries=0)

    assert chain.invoke("prompt") is None
    assert a._model.invoke_count == 1
    assert b._model.invoke_count == 1


def test_chain_no_available_providers_returns_none():
    a = _fake_client("a", available=False)
    b = _fake_client("b", available=False)
    chain = LLMChain([a, b], retries=0)

    assert chain.invoke("prompt") is None


def test_chain_empty_returns_none():
    assert LLMChain([], retries=0).invoke("prompt") is None


# ---------------------------------------------------------------------------
# Factory behaviour
# ---------------------------------------------------------------------------


def test_factory_forces_ollama_last():
    cfg = {
        "chain": ["groq", "ollama", "openrouter"],
        "retry": {"retries_per_provider": 0, "timeout_seconds": 5},
        "providers": {
            "groq": {"model": "x"},
            "openrouter": {"model": "x", "base_url": "http://x"},
            "ollama": {"model": "x", "base_url": "http://x"},
        },
    }
    # No env keys set -> all unavailable, but ordering still matters.
    os.environ.pop("GROQ_API_KEY", None)
    os.environ.pop("OPENROUTER_API_KEY", None)
    os.environ.pop("OPENCODE_GO_API_KEY", None)

    chain = build_chain(cfg)
    names = [c.name for c in chain.clients]
    assert names == ["groq", "openrouter", OLLAMA_NAME]


def test_factory_ollama_already_last_stays_last():
    cfg = {
        "chain": ["groq", "openrouter", "ollama"],
        "providers": {
            "groq": {"model": "x"},
            "openrouter": {"model": "x", "base_url": "http://x"},
            "ollama": {"model": "x", "base_url": "http://x"},
        },
    }
    chain = build_chain(cfg)
    names = [c.name for c in chain.clients]
    assert names == ["groq", "openrouter", OLLAMA_NAME]


def test_factory_skips_unknown_provider():
    cfg = {
        "chain": ["bogus", "groq"],
        "providers": {"groq": {"model": "x"}},
    }
    chain = build_chain(cfg)
    names = [c.name for c in chain.clients]
    assert "bogus" not in names
    assert OLLAMA_NAME in names  # ollama auto-appended


def test_factory_defaults_to_groq_ollama_when_chain_missing():
    cfg = {"providers": {"groq": {"model": "x"}}}
    chain = build_chain(cfg)
    names = [c.name for c in chain.clients]
    assert names == ["groq", OLLAMA_NAME]


def test_factory_negative_retries_clamped_to_zero():
    cfg = {
        "chain": ["groq"],
        "retry": {"retries_per_provider": -3},
        "providers": {"groq": {"model": "x"}},
    }
    chain = build_chain(cfg)
    assert chain._retries == 0


# ---------------------------------------------------------------------------
# Provider builders - availability logic (no network/keys)
# ---------------------------------------------------------------------------


def test_groq_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    client = build_groq({"model": "llama-3.1-8b-instant"}, timeout=10)
    assert client.is_available() is False
    assert "GROQ_API_KEY" in (client.describe_unavailable() or "")


def test_groq_unavailable_without_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-key")
    client = build_groq({}, timeout=10)
    assert client.is_available() is False


def test_groq_available_with_key_and_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake-key")
    client = build_groq({"model": "llama-3.1-8b-instant"}, timeout=10)
    assert client.is_available() is True
    assert client.name == "groq"


def test_openrouter_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client = build_openrouter(
        {"model": "openai/gpt-4o-mini", "base_url": "https://openrouter.ai/api/v1"},
        timeout=10,
    )
    assert client.is_available() is False


def test_openrouter_unavailable_without_base_url(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
    client = build_openrouter({"model": "openai/gpt-4o-mini"}, timeout=10)
    assert client.is_available() is False


def test_openrouter_available_with_full_config(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
    client = build_openrouter(
        {
            "model": "openai/gpt-4o-mini",
            "base_url": "https://openrouter.ai/api/v1",
            "http_referer": "https://example.com",
            "x_title": "soc-triage",
        },
        timeout=10,
    )
    assert client.is_available() is True


def test_opencode_go_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("OPENCODE_GO_API_KEY", raising=False)
    client = build_opencode_go(
        {"model": "glm-5.2", "base_url": "https://example.com/v1"},
        timeout=10,
    )
    assert client.is_available() is False


def test_opencode_go_unavailable_without_base_url(monkeypatch):
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "fake-key")
    client = build_opencode_go({"model": "glm-5.2"}, timeout=10)
    assert client.is_available() is False


def test_opencode_go_unavailable_without_model(monkeypatch):
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "fake-key")
    client = build_opencode_go(
        {"base_url": "https://example.com/v1"},
        timeout=10,
    )
    assert client.is_available() is False


def test_opencode_go_available_with_full_config(monkeypatch):
    monkeypatch.setenv("OPENCODE_GO_API_KEY", "fake-key")
    client = build_opencode_go(
        {"model": "glm-5.2", "base_url": "https://example.com/v1"},
        timeout=10,
    )
    assert client.is_available() is True


def test_ollama_unavailable_without_model():
    client = build_ollama({"base_url": "http://localhost:11434"}, timeout=10)
    assert client.is_available() is False


def test_ollama_unavailable_without_base_url():
    client = build_ollama({"model": "gemma3:4b"}, timeout=10)
    assert client.is_available() is False


def test_ollama_available_with_full_config():
    client = build_ollama(
        {"model": "gemma3:4b", "base_url": "http://localhost:11434"},
        timeout=10,
    )
    # Construction should succeed even if Ollama isn't running locally;
    # availability is about config completeness, not reachability.
    assert client.is_available() is True


# ---------------------------------------------------------------------------
# LLMClient edge cases
# ---------------------------------------------------------------------------


def test_client_invoke_wraps_model_exception_as_provider_error():
    class _Boom:
        def invoke(self, messages):
            raise RuntimeError("network down")

    client = LLMClient("boom", _Boom(), available=True)
    with pytest.raises(ProviderError, match="boom invoke failed"):
        client.invoke("prompt")


def test_client_invoke_rejects_empty_content():
    class _Empty:
        def invoke(self, messages):
            return type("Resp", (), {"content": "   "})()

    client = LLMClient("empty", _Empty(), available=True)
    with pytest.raises(ProviderError, match="empty content"):
        client.invoke("prompt")


def test_client_invoke_coerces_non_string_content():
    class _NonStr:
        def invoke(self, messages):
            return type("Resp", (), {"content": {"some": "dict"}})()

    client = LLMClient("nonstr", _NonStr(), available=True)
    assert "some" in client.invoke("prompt")


def test_client_unavailable_invoke_raises():
    client = LLMClient("x", None, available=False)
    with pytest.raises(ProviderError, match="x not available"):
        client.invoke("prompt")
