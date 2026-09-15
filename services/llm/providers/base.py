"""LLM Provider Protocol.

Structural subtyping — any class with chat() and complete() is a provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class LLMResult:
    """Inference result with token accounting."""

    text: str
    tokens_used: int


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM providers.

    All providers must implement:
    - chat(): send messages (optionally multimodal) and receive a response
    - complete(): complete a prompt
    """

    def chat(self, messages: list[dict], context: str | None = None) -> LLMResult:
        """Send chat messages and receive a response.

        Args:
            messages: List of message dicts with 'role' and 'content'
                      (content may be a string or multimodal parts).
            context: Optional RAG context to inject.

        Returns:
            LLMResult with response text and tokens_used.
        """
        ...

    def complete(self, prompt: str) -> LLMResult:
        """Complete a prompt.

        Args:
            prompt: The prompt to complete.

        Returns:
            LLMResult with completion text and tokens_used.
        """
        ...
