"""Build an ``LLMChain`` from the ``llm`` section of settings.yaml.

Config schema (see ``backend/config/settings.yaml``)::

    llm:
      chain: [groq, openrouter, opencode_go, ollama]
      retry:
        retries_per_provider: 1
        timeout_seconds: 30
      providers:
        groq:        {model, temperature}
        openrouter:  {model, base_url, temperature, http_referer, x_title}
        opencode_go: {model, base_url, temperature}
        ollama:      {model, base_url, temperature}
"""

from __future__ import annotations

import logging
from typing import Any

from dotenv import load_dotenv

from triage.llm.base import LLMClient
from triage.llm.chain import LLMChain
from triage.llm.providers import OLLAMA_NAME, PROVIDER_BUILDERS

logger = logging.getLogger(__name__)


def _force_ollama_last(chain_names: list[str]) -> list[str]:
    """Always treat ``ollama`` as the final LLM safety-net before deterministic fallback."""
    filtered = [name for name in chain_names if name != OLLAMA_NAME]
    filtered.append(OLLAMA_NAME)
    return filtered


def build_chain(llm_config: dict[str, Any]) -> LLMChain:
    # Load backend/.env so provider API keys are visible to os.getenv() in builders.
    # Safe to call multiple times; python-dotenv no-ops if already loaded.
    load_dotenv()

    chain_names: list[str] = list(llm_config.get("chain") or ["groq", "ollama"])
    chain_names = _force_ollama_last(chain_names)

    retry_cfg = llm_config.get("retry") or {}
    retries = int(retry_cfg.get("retries_per_provider", 0) or 0)
    timeout = float(retry_cfg.get("timeout_seconds", 30) or 30)

    providers_cfg = llm_config.get("providers") or {}

    clients: list[LLMClient] = []
    for name in chain_names:
        builder = PROVIDER_BUILDERS.get(name)
        if builder is None:
            logger.warning("factory: unknown provider %r in chain; skipping", name)
            continue
        provider_cfg = providers_cfg.get(name) or {}
        try:
            client = builder(provider_cfg, timeout)
        except Exception as exc:  # noqa: BLE001 - defensive: never crash the agent
            logger.warning("factory: %s builder raised %s; marking unavailable", name, exc)
            client = LLMClient(name, None, available=False, unavailable_reason=f"builder raised: {exc}")
        clients.append(client)
        logger.debug("factory: %s -> %s", name, client.describe_unavailable())

    return LLMChain(clients=clients, retries=retries)
