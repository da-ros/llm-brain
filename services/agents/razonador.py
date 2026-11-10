"""Razonador nodes — retrieve → generate → extract_assumptions."""

from __future__ import annotations

from typing import Any

from base import NO_PERSONAL_CONTEXT
from exceptions import LLMTimeoutError, LLMUpstreamError
from logging_setup import log_with_correlation
from tools import cited_sources, invoke_tool


async def retrieve_context(state: dict[str, Any]) -> dict[str, Any]:
    """Razonador retrieve node via rag_search (HTTP RAG 8002)."""
    correlation_id = state.get("correlation_id") or "no-id"
    log_with_correlation(correlation_id, "info", "reason_graph: retrieve_context")
    asked = (state.get("search_query") or "").strip()
    result = await invoke_tool(
        "rag_search",
        {
            "query": asked or (state.get("query") or ""),
            "user_id": state.get("user_id") or "",
            "correlation_id": correlation_id,
        },
    )
    return {
        "context": result.get("context") or "",
        "sources": result.get("sources") or [],
        "evidence": result.get("evidence") or [],
    }


async def generate_answer(state: dict[str, Any]) -> dict[str, Any]:
    """Razonador generate node via llm_generate (HTTP LLM /chat)."""
    correlation_id = state.get("correlation_id") or "no-id"
    log_with_correlation(correlation_id, "info", "reason_graph: generate_answer")
    try:
        result = await invoke_tool(
            "llm_generate",
            {
                "query": state.get("query") or "",
                "user_id": state.get("user_id") or "",
                "context": state.get("context") or "",
                "correlation_id": correlation_id,
            },
        )
    except LLMTimeoutError as exc:
        return {"error": str(exc), "error_kind": "timeout", "response": ""}
    except LLMUpstreamError as exc:
        return {"error": str(exc), "error_kind": "upstream", "response": ""}
    return {
        "response": result.get("response") or "",
        "tokens_used": int(result.get("tokens_used") or 0),
        "error": None,
        "error_kind": None,
    }


def route_after_generate(state: dict[str, Any]) -> str:
    """Conditional edge: LLM 5xx/timeout → error END, else assumptions."""
    if state.get("error"):
        return "error"
    return "assumptions"


async def extract_assumptions(state: dict[str, Any]) -> dict[str, Any]:
    """Record explicit assumptions; empty RAG must mention no personal context."""
    correlation_id = state.get("correlation_id") or "no-id"
    log_with_correlation(correlation_id, "info", "reason_graph: extract_assumptions")
    context = (state.get("context") or "").strip()
    evidence = state.get("evidence") or []
    sources = (
        cited_sources(evidence, state.get("response") or "")
        if evidence
        else (state.get("sources") or [])
    )
    assumptions: list[str] = []
    if not context or context == NO_PERSONAL_CONTEXT:
        assumptions.append(NO_PERSONAL_CONTEXT)
    else:
        assumptions.append("The answer is grounded in the user's retrieved personal documents.")
    if sources:
        assumptions.append(f"Retrieved {len(sources)} source(s) from RAG Top-k search.")
    if not assumptions:
        assumptions.append(NO_PERSONAL_CONTEXT)
    return {"assumptions": assumptions, "sources": sources}
