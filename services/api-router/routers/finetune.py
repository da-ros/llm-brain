"""Manual fine-tune trigger — premium only, forwards a ready Evaluador batch."""

from typing import Annotated

import httpx
from auth import require_premium
from config import get_settings
from fastapi import APIRouter, Depends, HTTPException, Request, status
from logging_setup import log_with_correlation
from pydantic import BaseModel
from rate_limit import rate_limit_tasks

router = APIRouter(prefix="/api", tags=["finetune"])


class FineTuneRequest(BaseModel):
    batch_id: str


@router.post("/finetune", status_code=status.HTTP_202_ACCEPTED)
async def trigger_finetune(
    request: Request,
    body: FineTuneRequest,
    user: Annotated[dict, Depends(require_premium)],
    _: Annotated[dict, Depends(rate_limit_tasks)],
):
    """Forward a ready batch to Agents POST /batches/{id}/trigger."""
    correlation_id = request.state.correlation_id
    settings = get_settings()
    log_with_correlation(
        correlation_id,
        "info",
        f"POST /api/finetune batch_id={body.batch_id}",
    )
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.AGENTS_SERVICE_URL}/batches/{body.batch_id}/trigger",
                json={
                    "user_id": user["user_id"],
                    "subscription_tier": "premium",
                },
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "error", f"Agents trigger failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Agents service error",
        ) from exc
    if response.status_code == status.HTTP_409_CONFLICT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Batch is empty, not ready, or already submitted",
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail="Fine-tune trigger failed",
        )
    data = response.json() or {}
    return {
        "job_id": data.get("job_id"),
        "status": data.get("status") or "submitted",
        "correlation_id": correlation_id,
    }
