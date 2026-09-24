"""Simulator Service errors."""

from __future__ import annotations


class SimulatorError(Exception):
    """Base error for the Simulator Service."""


class RAGTimeoutError(SimulatorError):
    """RAG Service timed out while hydration was required (HTTP 504)."""


class RAGUpstreamError(SimulatorError):
    """RAG Service returned 5xx or was unreachable (HTTP 502)."""


class LLMTimeoutError(SimulatorError):
    """LLM Service timed out (HTTP 504)."""


class LLMUpstreamError(SimulatorError):
    """LLM Service returned 5xx, was unreachable, or emitted invalid JSON (HTTP 502)."""


class InvalidScenarioJSONError(SimulatorError):
    """LLM text was not the required scenario JSON. Retried once, then 502."""
