"""Provider-agnostic LLM wrapper for the triage agent.

Public surface:
    build_chain(llm_config) -> LLMChain
    LLMChain.invoke(prompt) -> str | None
    LLMClient, ProviderError
"""

from triage.llm.base import LLMClient, ProviderError
from triage.llm.chain import LLMChain
from triage.llm.factory import build_chain

__all__ = ["LLMClient", "ProviderError", "LLMChain", "build_chain"]