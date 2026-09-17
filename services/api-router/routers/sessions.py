"""Session-end endpoint — premium only; notifies Evaluador."""

from typing import Annotated

import httpx
from auth import require_premium
from config import get_settings
from fastapi import APIRouter, Depends, HTTPException, Request, status
from logging_setup import log_with_correlation
from pydantic import BaseModel
from rate_limit import rate_limit_chat

router = APIRouter(prefix="/api", tags=["sessions"])


class SessionEndRequest(BaseModel):
    session_id: str


@router.post("/sessions/end", status_code=status.HTTP_202_ACCEPTED)
async def end_session(
    request: Request,
    body: SessionEndRequest,
    user: Annotated[dict, Depends(require_premium)],
    _: Annotated[dict, Depends(rate_limit_chat)],
):
    """Premium user ends a chat session so Evaluador can finalize feedback."""
    correlation_id = request.state.correlation_id
    settings = get_settings()
    log_with_correlation(
        correlation_id,
        "info",
        f"POST /api/sessions/end session_id={body.session_id}",
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{settings.AGENTS_SERVICE_URL}/sessions/end",
                json={
                    "user_id": user["user_id"],
                    "session_id": body.session_id,
                    "subscription_tier": "premium",
                },
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "error", f"Agents session-end failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Agents service error",
        ) from exc
    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail="Agents session-end failed",
        )
    return {"status": "accepted", "session_id": body.session_id, "correlation_id": correlation_id}
