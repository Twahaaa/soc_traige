"""Chain orchestrator: walks providers in order until one succeeds."""

from __future__ import annotations

import logging

from triage.llm.base import LLMClient, ProviderError

logger = logging.getLogger(__name__)


class LLMChain:
    """Invoke ``LLMClient`` instances in order until one returns content.

    Returns ``str`` on the first successful provider, ``None`` if every
    provider was unavailable or all attempts failed.
    """

    def __init__(self, clients: list[LLMClient], retries: int = 0) -> None:
        if retries < 0:
            retries = 0
        self._clients = list(clients)
        self._retries = retries

    @property
    def clients(self) -> list[LLMClient]:
        return list(self._clients)

    def invoke(self, prompt: str) -> str | None:
        attempted_any = False
        for client in self._clients:
            if not client.is_available():
                logger.debug("chain: skipping %s — %s", client.name, client.describe_unavailable())
                continue
            attempted_any = True
            attempts = 1 + self._retries
            for attempt in range(1, attempts + 1):
                try:
                    content = client.invoke(prompt)
                except ProviderError as exc:
                    logger.warning(
                        "chain: %s attempt %d/%d failed: %s",
                        client.name, attempt, attempts, exc,
                    )
                    continue
                logger.info("chain: %s succeeded on attempt %d/%d", client.name, attempt, attempts)
                return content
            logger.warning("chain: %s exhausted all %d attempt(s)", client.name, attempts)

        if not attempted_any:
            logger.warning("chain: no available LLM providers (all skipped)")
        else:
            logger.warning("chain: all available providers failed")
        return None
