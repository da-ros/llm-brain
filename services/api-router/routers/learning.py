"""Premium learning snapshot. Agents batches plus the memory count."""

from typing import Annotated, Any

import httpx
from auth import require_premium
from config import get_settings
from fastapi import APIRouter, Depends, HTTPException, Request, status
from logging_setup import log_with_correlation

router = APIRouter(prefix="/api", tags=["learning"])


async def _memory_count(user_id: str, correlation_id: str) -> int:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.RAG_SERVICE_URL}/documents",
                params={"user_id": user_id},
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "warning", f"Memory count skipped: {exc}")
        return 0
    if response.status_code != 200:
        return 0
    return len((response.json() or {}).get("documents") or [])


@router.get("/learning")
async def learning(
    request: Request,
    user: Annotated[dict, Depends(require_premium)],
) -> dict[str, Any]:
    """Recent turns, memories, batch readiness, and fine-tune history."""
    correlation_id = request.state.correlation_id
    settings = get_settings()
    user_id = user["user_id"]
    log_with_correlation(correlation_id, "info", "GET /api/learning")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"{settings.AGENTS_SERVICE_URL}/learning",
                params={"user_id": user_id},
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "error", f"Agents learning failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Agents service error",
        ) from exc
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Agents service error",
        )
    body = response.json() or {}
    body["memories"] = await _memory_count(user_id, correlation_id)
    return body
