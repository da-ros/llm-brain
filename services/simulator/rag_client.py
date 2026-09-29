"""HTTP client for RAG GET /search. The simulator never opens Chroma or GridFS."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import httpx
from config import get_settings
from exceptions import RAGTimeoutError, RAGUpstreamError
from logging_setup import log_with_correlation

_SLEEP = (
    re.compile(r"\b(?:slept|asleep)\b\D{0,24}(\d+(?:\.\d+)?)", re.I),
    re.compile(r"\bsleep\w*\b\D{0,24}(\d+(?:\.\d+)?)", re.I),
    re.compile(r"(\d+(?:\.\d+)?)\s*(?:hours|hour|h)\s+of\s+sleep", re.I),
)
_MEETINGS = (
    re.compile(r"(\d+(?:\.\d+)?)\s*(?:hours|hour|h)\s+of\s+meetings?", re.I),
    re.compile(r"\bmeetings?\b\D{0,24}(\d+(?:\.\d+)?)", re.I),
)
_FOCUS = (
    re.compile(r"(\d+(?:\.\d+)?)\s*(?:hours|hour|h)\s+of\s+focus", re.I),
    re.compile(r"\bfocus\b\D{0,24}(\d+(?:\.\d+)?)", re.I),
)
_SPEND = (
    re.compile(
        r"\b(?:spend|spent|spending|expense|invoice|budget)\b\D{0,20}\$?(\d+(?:\.\d+)?)",
        re.I,
    ),
    re.compile(r"\$(\d+(?:\.\d+)?)"),
)
_PRESCRIPTIONS = (
    re.compile(r"(\d+)\s+(?:active\s+)?(?:prescriptions?|medications?|medicines?)", re.I),
    re.compile(r"\b(?:prescriptions?|medications?|medicines?)\b\D{0,16}(\d+)", re.I),
)
_MEDICATION_WORD = re.compile(
    r"\b(?:prescription|medication|medicine|metformin|insulin)\b",
    re.I,
)


@dataclass
class RAGHydration:
    """Parsed personal context for one simulate call."""

    excerpts: str = ""
    sources: list[str] = field(default_factory=list)
    parsed: dict[str, float] = field(default_factory=dict)
    hit_count: int = 0


def _first_number(patterns: tuple[re.Pattern[str], ...], text: str) -> float | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return float(match.group(1))
    return None


def parse_rag_text(text: str) -> dict[str, float]:
    """Conservative regex extraction. Missing facts stay missing (defaults later)."""
    found: dict[str, float] = {}
    sleep = _first_number(_SLEEP, text)
    if sleep is not None:
        found["sleep_hours"] = sleep
    meetings = _first_number(_MEETINGS, text)
    if meetings is not None:
        found["meeting_hours_per_day"] = meetings
    focus = _first_number(_FOCUS, text)
    if focus is not None:
        found["focus_hours_per_day"] = focus
    spend = _first_number(_SPEND, text)
    if spend is not None:
        found["monthly_spend"] = spend
    prescriptions = _first_number(_PRESCRIPTIONS, text)
    if prescriptions is not None:
        found["active_prescriptions"] = prescriptions
    elif _MEDICATION_WORD.search(text):
        found["active_prescriptions"] = 1
    return found


def _source_of(item: dict[str, Any]) -> str:
    meta = item.get("metadata") or {}
    return str(
        meta.get("source") or meta.get("doc_id") or meta.get("gridfs_id") or item.get("id") or ""
    )


async def hydrate(
    *,
    question: str,
    user_id: str,
    correlation_id: str,
) -> RAGHydration:
    """GET RAG /search. 5xx → RAGUpstreamError, timeout → RAGTimeoutError."""
    settings = get_settings()
    url = f"{settings.RAG_SERVICE_URL}/search"
    log_with_correlation(
        correlation_id,
        "info",
        f"RAG hydrate → GET {url} user_id={user_id}",
    )
    try:
        async with httpx.AsyncClient(timeout=settings.RAG_TIMEOUT_SECONDS) as client:
            response = await client.get(
                url,
                params={"query": question, "user_id": user_id, "k": settings.RAG_TOP_K},
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.TimeoutException as exc:
        log_with_correlation(correlation_id, "error", "RAG hydrate timeout")
        raise RAGTimeoutError("RAG service timeout") from exc
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "error", f"RAG hydrate error: {exc}")
        raise RAGUpstreamError(f"RAG service error: {exc}") from exc

    if response.status_code == 504:
        log_with_correlation(correlation_id, "error", "RAG hydrate HTTP 504")
        raise RAGTimeoutError("RAG service timeout")
    if response.status_code >= 500:
        log_with_correlation(
            correlation_id,
            "error",
            f"RAG hydrate HTTP {response.status_code}",
        )
        raise RAGUpstreamError(f"RAG service HTTP {response.status_code}")
    if response.status_code != 200:
        log_with_correlation(
            correlation_id,
            "error",
            f"RAG hydrate HTTP {response.status_code}",
        )
        raise RAGUpstreamError(f"RAG service HTTP {response.status_code}")

    data = response.json() or {}
    results = data.get("results") or []
    parts: list[str] = []
    sources: list[str] = []
    for index, item in enumerate(results, 1):
        meta = item.get("metadata") or {}
        text = item.get("document") or meta.get("chunk_text") or meta.get("text") or ""
        source = _source_of(item)
        if source and source not in sources:
            sources.append(source)
        if text:
            parts.append(f"[{index}] {text}")
    excerpts = "\n".join(parts)
    parsed = parse_rag_text(excerpts)
    if results:
        log_with_correlation(
            correlation_id,
            "info",
            f"RAG hydrate returned {len(results)} hits",
        )
    else:
        log_with_correlation(
            correlation_id,
            "info",
            "RAG hydrate empty — applying defaults",
        )
    return RAGHydration(
        excerpts=excerpts,
        sources=sources,
        parsed=parsed,
        hit_count=len(results),
    )
