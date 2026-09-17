"""Local MCP tool contracts wrapping RAG, LLM, MongoDB, and Fine-Tune over HTTP.

No third-party MCP servers. LangGraph nodes invoke these tools by name.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from config import get_settings
from exceptions import LLMTimeoutError, LLMUpstreamError, UnknownToolError
from logging_setup import log_with_correlation

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "rag_search",
        "owner": "Razonador",
        "description": "Top-k multimodal retrieval from RAG Service (port 8002).",
        "wraps": "RAG Service GET /search",
        "input_schema": {"query": "str", "user_id": "str", "correlation_id": "str"},
    },
    {
        "name": "llm_generate",
        "owner": "Razonador",
        "description": "Multimodal Qwen3.5-4B inference via LLM Service (port 8003).",
        "wraps": "LLM Service POST /chat",
        "input_schema": {
            "query": "str",
            "user_id": "str",
            "context": "str",
            "correlation_id": "str",
        },
    },
    {
        "name": "ingest_turn",
        "owner": "Ingestor",
        "description": "Persist a completed premium chat turn in agent_interactions.",
        "wraps": "MongoDB agent_interactions",
        "input_schema": {
            "user_id": "str",
            "session_id": "str",
            "correlation_id": "str",
            "query": "str",
            "response": "str",
            "assumptions": "list[str]",
            "sources": "list[str]",
        },
    },
    {
        "name": "evaluate_turn",
        "owner": "Evaluador",
        "description": (
            "Score a turn into agent_feedback and optionally append the weekly "
            "finetune_batches document. Never calls Fine-Tune POST /train."
        ),
        "wraps": "MongoDB agent_feedback, finetune_batches",
        "input_schema": {
            "op": "score | append_batch",
            "user_id": "str",
            "correlation_id": "str",
            "session_id": "str",
            "query": "str",
            "response": "str",
            "assumptions": "list[str]",
        },
    },
    {
        "name": "finetune_trigger",
        "owner": "Evaluador",
        "description": "Manual local LoRA trigger via Fine-Tune Service (port 8004).",
        "wraps": "Fine-Tune Service POST /train",
        "input_schema": {"user_id": "str", "dataset_path": "str", "correlation_id": "str"},
    },
]


def list_tools() -> list[dict[str, Any]]:
    """Return the MCP tool registry (name, description, input schema)."""
    return list(TOOL_DEFINITIONS)


def _headers(correlation_id: str) -> dict[str, str]:
    return {"X-Request-ID": correlation_id or "no-id"}


async def rag_search(arguments: dict[str, Any]) -> dict[str, Any]:
    """HTTP GET RAG /search with X-Request-ID and user_id."""
    settings = get_settings()
    query = arguments.get("query") or ""
    user_id = arguments.get("user_id") or ""
    correlation_id = arguments.get("correlation_id") or "no-id"
    log_with_correlation(
        correlation_id,
        "info",
        f"MCP rag_search → RAG {settings.RAG_SERVICE_URL}/search user_id={user_id}",
    )
    try:
        async with httpx.AsyncClient(timeout=settings.RAG_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{settings.RAG_SERVICE_URL}/search",
                params={"query": query, "user_id": user_id},
                headers=_headers(correlation_id),
            )
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "warning", f"RAG search failed: {exc}")
        return {"context": "", "sources": [], "results": []}

    if response.status_code != 200:
        log_with_correlation(
            correlation_id,
            "warning",
            f"RAG search HTTP {response.status_code} — continuing without context",
        )
        return {"context": "", "sources": [], "results": []}

    data = response.json() or {}
    results = data.get("results") or []
    sources: list[str] = []
    parts: list[str] = []
    for index, item in enumerate(results, 1):
        meta = item.get("metadata") or {}
        text = item.get("document") or meta.get("chunk_text") or meta.get("text") or ""
        source = meta.get("source") or meta.get("doc_id") or meta.get("gridfs_id") or ""
        if source:
            sources.append(str(source))
        if text:
            parts.append(f"[{index}] {text}")
    return {"context": "\n".join(parts), "sources": sources, "results": results}


async def llm_generate(arguments: dict[str, Any]) -> dict[str, Any]:
    """HTTP POST LLM /chat (Qwen3.5-4B). Timeout → 504, 5xx → 502."""
    settings = get_settings()
    query = arguments.get("query") or ""
    user_id = arguments.get("user_id") or ""
    context = arguments.get("context") or None
    correlation_id = arguments.get("correlation_id") or "no-id"
    log_with_correlation(
        correlation_id,
        "info",
        f"MCP llm_generate → LLM {settings.LLM_SERVICE_URL}/chat (Qwen3.5-4B)",
    )
    payload = {
        "messages": [{"role": "user", "content": query}],
        "user_id": user_id,
        "tier": "premium",
        "context": context,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{settings.LLM_SERVICE_URL}/chat",
                json=payload,
                headers=_headers(correlation_id),
            )
    except httpx.TimeoutException as exc:
        log_with_correlation(correlation_id, "error", "LLM service timeout")
        raise LLMTimeoutError("LLM service timeout") from exc
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "error", f"LLM service error: {exc}")
        raise LLMUpstreamError(f"LLM service error: {exc}") from exc

    if response.status_code >= 500:
        log_with_correlation(
            correlation_id,
            "error",
            f"LLM service HTTP {response.status_code}",
        )
        if response.status_code == 504:
            raise LLMTimeoutError("LLM service timeout")
        raise LLMUpstreamError(f"LLM service HTTP {response.status_code}")
    if response.status_code != 200:
        raise LLMUpstreamError(f"LLM service HTTP {response.status_code}")

    data = response.json() or {}
    return {
        "response": data.get("response") or "",
        "tokens_used": int(data.get("tokens_used") or 0),
    }


async def ingest_turn(arguments: dict[str, Any]) -> dict[str, Any]:
    """Upsert agent_interactions (idempotent on correlation_id)."""
    import db

    correlation_id = arguments.get("correlation_id") or "no-id"
    log_with_correlation(correlation_id, "info", "MCP ingest_turn → MongoDB agent_interactions")
    stored = await db.upsert_interaction(
        {
            "user_id": arguments.get("user_id"),
            "session_id": arguments.get("session_id"),
            "correlation_id": correlation_id,
            "query": arguments.get("query") or "",
            "response": arguments.get("response") or "",
            "assumptions": arguments.get("assumptions") or [],
            "sources": arguments.get("sources") or [],
        }
    )
    return {"interaction": stored, "correlation_id": correlation_id}


def heuristic_score(response: str, assumptions: list[str]) -> tuple[float, str, bool]:
    """Deterministic Evaluador score. No extra LLM call, never trains."""
    settings = get_settings()
    score = 0.0
    reasons: list[str] = []
    if (response or "").strip():
        score += 0.5
        reasons.append("non-empty answer")
    else:
        reasons.append("empty answer")
    if assumptions:
        score += 0.5
        reasons.append("assumptions present")
    else:
        reasons.append("missing assumptions")
    include = score >= settings.EVAL_SCORE_THRESHOLD
    return score, "; ".join(reasons), include


async def evaluate_turn(arguments: dict[str, Any]) -> dict[str, Any]:
    """Score + persist feedback, or append the weekly batch. Never POST /train."""
    import db

    op = arguments.get("op") or "score"
    correlation_id = arguments.get("correlation_id") or "no-id"
    user_id = arguments.get("user_id") or ""
    if op == "append_batch":
        log_with_correlation(
            correlation_id,
            "info",
            "MCP evaluate_turn append_batch → MongoDB finetune_batches (no POST /train)",
        )
        batch = await db.append_batch_item(
            user_id=user_id,
            item={
                "correlation_id": correlation_id,
                "session_id": arguments.get("session_id"),
                "query": arguments.get("query") or "",
                "response": arguments.get("response") or "",
                "assumptions": arguments.get("assumptions") or [],
            },
        )
        return {"batch": batch, "status": batch.get("status")}

    score, reason, include = heuristic_score(
        arguments.get("response") or "",
        arguments.get("assumptions") or [],
    )
    log_with_correlation(
        correlation_id,
        "info",
        f"MCP evaluate_turn score={score:.2f} include={include} (never POST /train)",
    )
    feedback = await db.upsert_feedback(
        {
            "user_id": user_id,
            "correlation_id": correlation_id,
            "session_id": arguments.get("session_id"),
            "score": score,
            "reason": reason,
            "should_include_in_batch": include,
        }
    )
    return {
        "score": score,
        "reason": reason,
        "should_include_in_batch": include,
        "feedback": feedback,
    }


async def finetune_trigger(arguments: dict[str, Any]) -> dict[str, Any]:
    """HTTP POST Fine-Tune /train (manual path only)."""
    settings = get_settings()
    user_id = arguments.get("user_id") or ""
    dataset_path = arguments.get("dataset_path") or ""
    correlation_id = arguments.get("correlation_id") or "no-id"
    log_with_correlation(
        correlation_id,
        "info",
        f"MCP finetune_trigger → Fine-Tune {settings.FINETUNE_SERVICE_URL}/train",
    )
    try:
        async with httpx.AsyncClient(timeout=settings.FINETUNE_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{settings.FINETUNE_SERVICE_URL}/train",
                json={"user_id": user_id, "dataset_path": dataset_path},
                headers=_headers(correlation_id),
            )
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "error", f"Fine-Tune service error: {exc}")
        raise LLMUpstreamError(f"Fine-Tune service error: {exc}") from exc

    if response.status_code >= 400:
        log_with_correlation(
            correlation_id,
            "error",
            f"Fine-Tune HTTP {response.status_code}",
        )
        raise LLMUpstreamError(f"Fine-Tune HTTP {response.status_code}")
    data = response.json() or {}
    return {
        "job_id": data.get("job_id") or "",
        "status": data.get("status") or "submitted",
    }


HANDLERS: dict[str, ToolHandler] = {
    "rag_search": rag_search,
    "llm_generate": llm_generate,
    "ingest_turn": ingest_turn,
    "evaluate_turn": evaluate_turn,
    "finetune_trigger": finetune_trigger,
}


async def invoke_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dispatch an MCP tool by name. Unknown names raise UnknownToolError."""
    handler = HANDLERS.get(name)
    if handler is None:
        raise UnknownToolError(name)
    return await handler(arguments or {})
