"""Shield Service errors."""

from __future__ import annotations


class ShieldError(Exception):
    """Base error for the Shield Service."""


class EmbedTimeoutError(ShieldError):
    """RAG POST /embed timed out."""


class EmbedUpstreamError(ShieldError):
    """RAG POST /embed returned 5xx or was unreachable."""


class LLMTimeoutError(ShieldError):
    """LLM Service timed out (HTTP 504)."""


class LLMUpstreamError(ShieldError):
    """LLM Service returned 5xx, was unreachable, or emitted invalid JSON (HTTP 502)."""


class InvalidVerdictJSONError(ShieldError):
    """LLM text was not the required verdict JSON. Retried once, then 502."""
