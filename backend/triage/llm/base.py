"""Adapter interface for LLM providers used by the triage agent."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    """Raised when a provider invocation fails (auth, network, timeout, parse)."""


class LLMClient:
    """Thin adapter around a langchain ``BaseChatModel``.

    Each provider builder constructs one ``LLMClient``. The chain walks a list
    of these, skipping any that are unavailable and falling back on errors.
    """

    def __init__(
        self,
        name: str,
        model: Any | None,
        *,
        available: bool,
        unavailable_reason: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.name = name
        self._model = model
        self._available = available
        self._unavailable_reason = unavailable_reason
        self._timeout = timeout_seconds

    def is_available(self) -> bool:
        return self._available and self._model is not None

    def describe_unavailable(self) -> str:
        if self.is_available():
            return f"{self.name}: available"
        return f"{self.name}: unavailable ({self._unavailable_reason or 'no model'})"

    def invoke(self, prompt: str) -> str:
        """Invoke the underlying model and return its textual content.

        Raises ``ProviderError`` on any failure so the chain can move on.
        """
        if not self.is_available():
            raise ProviderError(f"{self.name} not available")
        try:
            response = self._model.invoke([HumanMessage(content=prompt)])
        except Exception as exc:  # noqa: BLE001 - we want to wrap *all* failures
            raise ProviderError(f"{self.name} invoke failed: {exc}") from exc
        content = getattr(response, "content", response)
        if not isinstance(content, str):
            try:
                content = str(content)
            except Exception as exc:  # noqa: BLE001
                raise ProviderError(f"{self.name} returned non-string content: {exc}") from exc
        if not content.strip():
            raise ProviderError(f"{self.name} returned empty content")
        return content
