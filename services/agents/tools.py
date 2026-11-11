"""Local MCP tool contracts wrapping RAG, LLM, MongoDB, and Fine-Tune over HTTP.

No third-party MCP servers. LangGraph nodes invoke these tools by name.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from base import NO_PERSONAL_CONTEXT
from config import get_settings
from exceptions import LLMTimeoutError, LLMUpstreamError, UnknownToolError
from fastapi import HTTPException
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
    {
        "name": "simulate_whatif",
        "owner": "Simulator",
        "description": "What-if scenarios via Simulator Service (port 8007). Not used by reason_graph.",
        "wraps": "Simulator Service POST /simulate",
        "input_schema": {
            "user_id": "str",
            "question": "str",
            "variables": "dict",
            "subscription_tier": "str",
            "correlation_id": "str",
        },
    },
    {
        "name": "scan_message",
        "owner": "Shield",
        "description": "Phishing and scam scan via Shield Service (port 8009). Not used by reason_graph.",
        "wraps": "Shield Service POST /scan",
        "input_schema": {
            "user_id": "str",
            "text": "str",
            "source": "str",
            "subscription_tier": "str",
            "correlation_id": "str",
        },
    },
    {
        "name": "analytics_query",
        "owner": "Analytics",
        "description": "Pearson correlations via Analytics Service (port 8008). Not used by reason_graph.",
        "wraps": "Analytics Service GET /correlations",
        "input_schema": {
            "user_id": "str",
            "subscription_tier": "str",
            "correlation_id": "str",
        },
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
    evidence: list[dict[str, str]] = []
    for item in results:
        meta = item.get("metadata") or {}
        text = item.get("document") or meta.get("chunk_text") or meta.get("text") or ""
        source = meta.get("source") or meta.get("doc_id") or meta.get("gridfs_id") or ""
        if _bare_fact(text):
            continue
        if source:
            sources.append(str(source))
        if text:
            statement = _with_source(text, str(source))
            parts.append(f"[{len(parts) + 1}] {statement}")
            evidence.append({"source": str(source), "text": text})
    return {
        "context": "\n".join(parts),
        "sources": sources,
        "evidence": evidence,
        "results": results,
    }


_CONTENT_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "of",
        "to",
        "and",
        "or",
        "in",
        "on",
        "for",
        "with",
        "from",
        "that",
        "this",
        "it",
        "be",
        "thing",
        "things",
        "at",
        "by",
        "as",
        "into",
        "over",
        "than",
        "then",
        "also",
        "not",
        "no",
        "yes",
    }
)


def _with_source(text: str, source: str) -> str:
    """Keep the filename on the line the model reads. Search never sees it."""
    label = (source or "").strip()
    if not label:
        return text
    return f"{text} (source: {label})"


def _file_extension(source: str) -> str:
    """The format is the filename suffix, such as mp4 or mpeg."""
    name = (source or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    if "." not in name:
        return ""
    suffix = name.rsplit(".", 1)[-1].strip(".,;:\"'()[]")
    if len(suffix) < 2 or suffix in _CONTENT_STOPWORDS:
        return ""
    return suffix


def _content_words(text: str) -> list[str]:
    words = []
    for raw in (text or "").lower().split():
        token = raw.strip(".,;:\"'()[]")
        if token and token not in _CONTENT_STOPWORDS:
            words.append(token)
    return words


_TYPE_WORDS = frozenset(
    {"thing", "things", "person", "place", "date", "time", "organization", "organisation"}
)


def _bare_fact(text: str) -> bool:
    """A line that only labels a type does not say what happened."""
    words = [word.strip(".,;:\"'()[]").lower() for word in (text or "").split()]
    words = [word for word in words if word]
    if not words or words[-1] not in _TYPE_WORDS:
        return False
    return len(words) == 1 or words[-2] in {"a", "an", "is", "are"}


def _words_needed(fact_word_count: int) -> int:
    """A long passage must share more than a place and a year."""
    if fact_word_count <= 1:
        return 1
    if fact_word_count >= 12:
        return 4
    return 2


def cited_sources(evidence: list[dict[str, str]], answer: str) -> list[str]:
    """Files whose fact, or whose format, shares words with the sentence that was said."""
    answer_words = set(_content_words(answer))
    sources: list[str] = []
    for item in evidence:
        source = (item.get("source") or "").strip()
        fact_words = list(dict.fromkeys(_content_words(item.get("text") or "")))
        overlap = [word for word in fact_words if word in answer_words]
        names_format = _file_extension(source) in answer_words
        if not names_format and len(overlap) < _words_needed(len(fact_words)):
            continue
        if source and source not in sources:
            sources.append(source)
    return sources


_DIRECT_ANSWER = (
    "Reply in plain sentences. State the fact. "
    "When you give a date, copy that date from the statements. "
    "Do not mention the context, the numbered statements, or how the answer was found."
)


def _direct_question(query: str) -> str:
    """Keep the transcript, then tell the model to answer in a sentence."""
    text = (query or "").rstrip()
    if text.endswith(_DIRECT_ANSWER):
        return text
    if not text:
        return _DIRECT_ANSWER
    return f"{text}\n\n{_DIRECT_ANSWER}"


async def llm_generate(arguments: dict[str, Any]) -> dict[str, Any]:
    """HTTP POST LLM /chat (Qwen3.5-4B). Timeout → 504, 5xx → 502."""
    settings = get_settings()
    query = _direct_question(arguments.get("query") or "")
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
    personal = [
        item for item in assumptions if (item or "").strip() and item != NO_PERSONAL_CONTEXT
    ]
    if personal:
        score += 0.5
        reasons.append("personal context")
    else:
        reasons.append("no personal facts")
    include = score >= settings.EVAL_SCORE_THRESHOLD
    return score, "; ".join(reasons), include


async def evaluate_turn(arguments: dict[str, Any]) -> dict[str, Any]:
    """Score + persist feedback, or append the open batch. Never POST /train."""
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


async def simulate_whatif(arguments: dict[str, Any]) -> dict[str, Any]:
    """HTTP POST Simulator /simulate. Timeout → 504, 5xx → 502. Does not invent scenarios."""
    settings = get_settings()
    correlation_id = arguments.get("correlation_id") or "no-id"
    log_with_correlation(
        correlation_id,
        "info",
        f"MCP simulate_whatif → Simulator {settings.SIMULATOR_SERVICE_URL}/simulate",
    )
    payload = {
        "user_id": arguments.get("user_id") or "",
        "subscription_tier": arguments.get("subscription_tier") or "premium",
        "question": arguments.get("question") or "",
        "variables": arguments.get("variables") or {},
    }
    try:
        async with httpx.AsyncClient(timeout=settings.SIMULATOR_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{settings.SIMULATOR_SERVICE_URL}/simulate",
                json=payload,
                headers=_headers(correlation_id),
            )
    except httpx.TimeoutException as exc:
        log_with_correlation(correlation_id, "error", "Simulator service timeout")
        raise LLMTimeoutError("Simulator service timeout") from exc
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "error", f"Simulator service error: {exc}")
        raise LLMUpstreamError(f"Simulator service error: {exc}") from exc

    if response.status_code == 504:
        log_with_correlation(correlation_id, "error", "Simulator service HTTP 504")
        raise LLMTimeoutError("Simulator service timeout")
    if response.status_code >= 500:
        log_with_correlation(
            correlation_id,
            "error",
            f"Simulator service HTTP {response.status_code}",
        )
        raise LLMUpstreamError(f"Simulator service HTTP {response.status_code}")
    if response.status_code >= 400:
        detail = "Simulator service error"
        try:
            body = response.json() or {}
            detail = body.get("detail") or detail
        except Exception:
            detail = response.text or detail
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json() or {}


async def scan_message(arguments: dict[str, Any]) -> dict[str, Any]:
    """HTTP POST Shield /scan. Timeout → 504, 5xx → 502. Does not invent an alert."""
    settings = get_settings()
    correlation_id = arguments.get("correlation_id") or "no-id"
    log_with_correlation(
        correlation_id,
        "info",
        f"MCP scan_message → Shield {settings.SHIELD_SERVICE_URL}/scan",
    )
    payload = {
        "user_id": arguments.get("user_id") or "",
        "subscription_tier": arguments.get("subscription_tier") or "premium",
        "source": arguments.get("source") or "message",
        "text": arguments.get("text") or "",
        "filename": arguments.get("filename") or "",
        "content_base64": arguments.get("content_base64") or "",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.SHIELD_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{settings.SHIELD_SERVICE_URL}/scan",
                json=payload,
                headers=_headers(correlation_id),
            )
    except httpx.TimeoutException as exc:
        log_with_correlation(correlation_id, "error", "Shield service timeout")
        raise LLMTimeoutError("Shield service timeout") from exc
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "error", f"Shield service error: {exc}")
        raise LLMUpstreamError(f"Shield service error: {exc}") from exc

    if response.status_code == 504:
        log_with_correlation(correlation_id, "error", "Shield service HTTP 504")
        raise LLMTimeoutError("Shield service timeout")
    if response.status_code >= 500:
        log_with_correlation(
            correlation_id,
            "error",
            f"Shield service HTTP {response.status_code}",
        )
        raise LLMUpstreamError(f"Shield service HTTP {response.status_code}")
    if response.status_code >= 400:
        detail = "Shield service error"
        try:
            body = response.json() or {}
            detail = body.get("detail") or detail
        except Exception:
            detail = response.text or detail
        raise HTTPException(status_code=response.status_code, detail=detail)
    data = response.json() or {}
    return {
        "alert": data.get("alert"),
        "severity": data.get("severity"),
        "reasons": data.get("reasons") or [],
        "likelihood": data.get("likelihood"),
        "summary": data.get("summary"),
        "llm_used": data.get("llm_used"),
    }


async def analytics_query(arguments: dict[str, Any]) -> dict[str, Any]:
    """HTTP GET Analytics /correlations. Timeout → 504, 5xx → 502. Does not invent r."""
    settings = get_settings()
    correlation_id = arguments.get("correlation_id") or "no-id"
    user_id = arguments.get("user_id") or ""
    log_with_correlation(
        correlation_id,
        "info",
        f"MCP analytics_query → Analytics {settings.ANALYTICS_SERVICE_URL}/correlations",
    )
    try:
        async with httpx.AsyncClient(timeout=settings.ANALYTICS_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{settings.ANALYTICS_SERVICE_URL}/correlations",
                params={
                    "user_id": user_id,
                    "subscription_tier": arguments.get("subscription_tier") or "premium",
                },
                headers=_headers(correlation_id),
            )
    except httpx.TimeoutException as exc:
        log_with_correlation(correlation_id, "error", "Analytics service timeout")
        raise LLMTimeoutError("Analytics service timeout") from exc
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "error", f"Analytics service error: {exc}")
        raise LLMUpstreamError(f"Analytics service error: {exc}") from exc

    if response.status_code == 504:
        log_with_correlation(correlation_id, "error", "Analytics service HTTP 504")
        raise LLMTimeoutError("Analytics service timeout")
    if response.status_code >= 500:
        log_with_correlation(
            correlation_id,
            "error",
            f"Analytics service HTTP {response.status_code}",
        )
        raise LLMUpstreamError(f"Analytics service HTTP {response.status_code}")
    if response.status_code >= 400:
        detail = "Analytics service error"
        try:
            body = response.json() or {}
            detail = body.get("detail") or detail
        except Exception:
            detail = response.text or detail
        raise HTTPException(status_code=response.status_code, detail=detail)
    data = response.json() or {}
    return {
        "pairs": data.get("pairs") or {},
        "narrative": data.get("narrative") or "",
        "llm_used": data.get("llm_used"),
    }


HANDLERS: dict[str, ToolHandler] = {
    "rag_search": rag_search,
    "llm_generate": llm_generate,
    "ingest_turn": ingest_turn,
    "evaluate_turn": evaluate_turn,
    "finetune_trigger": finetune_trigger,
    "simulate_whatif": simulate_whatif,
    "scan_message": scan_message,
    "analytics_query": analytics_query,
}


async def invoke_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dispatch an MCP tool by name. Unknown names raise UnknownToolError."""
    handler = HANDLERS.get(name)
    if handler is None:
        raise UnknownToolError(name)
    return await handler(arguments or {})
