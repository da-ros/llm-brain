"""LLM Provider Protocol.

Defines the interface for all LLM providers.
All providers must implement this protocol to be used by the application.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM providers.

    All providers must implement:
    - chat(): Send messages and receive a response
    - complete(): Complete a prompt
    """

    def chat(self, messages: list[dict], context: str | None = None) -> str:
        """Send chat messages and receive a response.

        Args:
            messages: List of message dicts with 'role' and 'content'
            context: Optional RAG context to inject

        Returns:
            The model's response as a string
        """
        ...

    def complete(self, prompt: str) -> str:
        """Complete a prompt.

        Args:
            prompt: The prompt to complete

        Returns:
            The completion as a string
        """
        ...
