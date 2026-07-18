"""Per-provider builders that construct ``LLMClient`` adapters from config.

Each builder is a callable taking the provider's sub-config dict (and the
shared retry/timeout settings) and returning an ``LLMClient``. Builders must
never raise — they return an unavailable client on any missing-required-field
or construction failure so the chain can skip gracefully.

Providers supported:
    groq         -> langchain_groq.ChatGroq
    openrouter   -> langchain_openai.ChatOpenAI (OpenAI-compatible)
    opencode_go  -> langchain_openai.ChatOpenAI (OpenAI-compatible)
    ollama       -> langchain_ollama.ChatOllama

Adding a new provider:
    1. write ``build_<name>(cfg, timeout)``
    2. register it in ``PROVIDER_BUILDERS``
    3. add it to the ``chain`` list in settings.yaml
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from triage.llm.base import LLMClient

logger = logging.getLogger(__name__)


def _env_key(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _float_or_default(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def build_groq(cfg: dict[str, Any], timeout: float | None) -> LLMClient:
    api_key = _env_key("GROQ_API_KEY")
    model_name = (cfg.get("model") or "").strip()
    if not api_key:
        return LLMClient("groq", None, available=False, unavailable_reason="GROQ_API_KEY not set")
    if not model_name:
        return LLMClient("groq", None, available=False, unavailable_reason="model not set in config")
    try:
        from langchain_groq import ChatGroq

        model = ChatGroq(
            model=model_name,
            api_key=api_key,
            temperature=_float_or_default(cfg.get("temperature")),
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("groq client construction failed: %s", exc)
        return LLMClient("groq", None, available=False, unavailable_reason=f"construction failed: {exc}")
    return LLMClient("groq", model, available=True, timeout_seconds=timeout)


def _build_openai_compatible(
    name: str,
    cfg: dict[str, Any],
    env_var: str,
    extra_headers: dict[str, str] | None,
    timeout: float | None,
) -> LLMClient:
    api_key = _env_key(env_var)
    model_name = (cfg.get("model") or "").strip()
    base_url = (cfg.get("base_url") or "").strip()
    if not api_key:
        return LLMClient(name, None, available=False, unavailable_reason=f"{env_var} not set")
    if not model_name:
        return LLMClient(name, None, available=False, unavailable_reason="model not set in config")
    if not base_url:
        return LLMClient(name, None, available=False, unavailable_reason="base_url not set in config")
    try:
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "model": model_name,
            "api_key": api_key,
            "base_url": base_url,
            "temperature": _float_or_default(cfg.get("temperature")),
            "timeout": timeout,
        }
        if extra_headers:
            kwargs["default_headers"] = extra_headers
        model = ChatOpenAI(**kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s client construction failed: %s", name, exc)
        return LLMClient(name, None, available=False, unavailable_reason=f"construction failed: {exc}")
    return LLMClient(name, model, available=True, timeout_seconds=timeout)


def build_openrouter(cfg: dict[str, Any], timeout: float | None) -> LLMClient:
    headers: dict[str, str] = {}
    referer = (cfg.get("http_referer") or "").strip()
    title = (cfg.get("x_title") or "").strip()
    if referer:
        headers["HTTP-Referer"] = referer
    if title:
        headers["X-Title"] = title
    return _build_openai_compatible(
        "openrouter", cfg, "OPENROUTER_API_KEY", headers or None, timeout
    )


def build_opencode_go(cfg: dict[str, Any], timeout: float | None) -> LLMClient:
    return _build_openai_compatible(
        "opencode_go", cfg, "OPENCODE_GO_API_KEY", None, timeout
    )


def build_ollama(cfg: dict[str, Any], timeout: float | None) -> LLMClient:
    model_name = (cfg.get("model") or "").strip()
    base_url = (cfg.get("base_url") or "").strip()
    if not model_name:
        return LLMClient("ollama", None, available=False, unavailable_reason="model not set in config")
    if not base_url:
        return LLMClient("ollama", None, available=False, unavailable_reason="base_url not set in config")
    try:
        from langchain_ollama import ChatOllama

        model = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=_float_or_default(cfg.get("temperature")),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ollama client construction failed: %s", exc)
        return LLMClient("ollama", None, available=False, unavailable_reason=f"construction failed: {exc}")
    return LLMClient("ollama", model, available=True, timeout_seconds=timeout)


PROVIDER_BUILDERS: dict[str, Callable[[dict[str, Any], float | None], LLMClient]] = {
    "groq": build_groq,
    "openrouter": build_openrouter,
    "opencode_go": build_opencode_go,
    "ollama": build_ollama,
}

OLLAMA_NAME = "ollama"
