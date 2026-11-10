"""LangGraph typed state for reason_graph and learn_graph."""

from __future__ import annotations

from typing import TypedDict


class ReasonState(TypedDict, total=False):
    """State for the sync Razonador graph (premium chat)."""

    user_id: str
    session_id: str
    correlation_id: str
    query: str
    search_query: str
    context: str
    sources: list[str]
    evidence: list[dict[str, str]]
    response: str
    assumptions: list[str]
    tokens_used: int
    error: str | None
    error_kind: str | None


class LearnState(TypedDict, total=False):
    """State for the async Ingestor + Evaluador graph (Kafka)."""

    user_id: str
    session_id: str
    correlation_id: str
    query: str
    response: str
    assumptions: list[str]
    sources: list[str]
    score: float
    should_include_in_batch: bool
    error: str | None
