"""HTTP client for RAG GET /search. Analytics never opens Chroma."""

from __future__ import annotations

import httpx
from config import get_settings
from logging_setup import log_with_correlation


async def excerpts(*, user_id: str, query: str, correlation_id: str) -> str:
    """Top-k text for this user_id. A RAG failure becomes an empty excerpt."""
    settings = get_settings()
    url = f"{settings.RAG_SERVICE_URL}/search"
    log_with_correlation(
        correlation_id,
        "info",
        f"RAG GET /search {url} user_id={user_id}",
    )
    try:
        async with httpx.AsyncClient(timeout=settings.RAG_TIMEOUT_SECONDS) as client:
            response = await client.get(
                url,
                params={"query": query[:500] or "life metrics", "user_id": user_id, "k": 3},
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "warning", f"RAG search failed: {exc}")
        return ""
    if response.status_code != 200:
        log_with_correlation(
            correlation_id,
            "warning",
            f"RAG search HTTP {response.status_code}",
        )
        return ""
    data = response.json() or {}
    parts: list[str] = []
    for index, item in enumerate(data.get("results") or [], 1):
        meta = item.get("metadata") or {}
        text = item.get("document") or meta.get("chunk_text") or meta.get("text") or ""
        if text:
            parts.append(f"[{index}] {text}")
    return "\n".join(parts)
