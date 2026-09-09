"""LLMProvider protocol (chat / completion interface)."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Chat/completion interface shared by on-device and local-container providers."""

    name: str

    def chat(self, messages: list[dict], context: str | None = None) -> str:
        """Send chat messages and receive a response.

        Args:
            messages: Message dicts with `role` and `content`.
            context: Optional RAG context to inject (Premium only).

        Returns:
            The model's response as a string.
        """
        ...

    def complete(self, prompt: str) -> str:
        """Complete a prompt and return the model output."""
        ...
