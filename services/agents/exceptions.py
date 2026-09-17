"""Agents Service errors."""

from __future__ import annotations


class AgentsError(Exception):
    """Base error for the Agents Service."""


class LLMTimeoutError(AgentsError):
    """LLM Service timed out (maps to HTTP 504)."""


class LLMUpstreamError(AgentsError):
    """LLM Service returned 5xx or was unreachable (maps to HTTP 502)."""


class UnknownToolError(AgentsError):
    """MCP tool name is not in the local registry."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)


class BatchNotReadyError(AgentsError):
    """Fine-tune batch is empty, not ready, or already submitted."""
