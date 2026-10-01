"""Premium analytics routes. Sync HTTP to Analytics Service. No Kafka."""

from typing import Annotated, Any

import httpx
from auth import require_premium
from config import get_settings
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from logging_setup import log_with_correlation
from rate_limit import rate_limit_analytics_ingest, rate_limit_analytics_query

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


async def _analytics(
    method: str,
    path: str,
    *,
    correlation_id: str,
    params: dict | None = None,
    data: dict | None = None,
    files: dict | None = None,
) -> Any:
    settings = get_settings()
    url = f"{settings.ANALYTICS_SERVICE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.request(
                method,
                url,
                params=params,
                data=data,
                files=files,
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.TimeoutException as exc:
        log_with_correlation(correlation_id, "error", "Analytics service timeout")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Analytics service timeout",
        ) from exc
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "error", f"Error calling Analytics service: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error calling Analytics service: {exc}",
        ) from exc

    if response.status_code == status.HTTP_504_GATEWAY_TIMEOUT:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Analytics service timeout",
        )
    if response.status_code >= 500:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Analytics service error",
        )
    if response.status_code >= 400:
        detail = "Analytics service error"
        try:
            detail = (response.json() or {}).get("detail") or detail
        except Exception:
            detail = response.text or detail
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


@router.post("/ingest")
async def ingest(
    request: Request,
    user: Annotated[dict, Depends(rate_limit_analytics_ingest)],
    file: UploadFile = File(...),
):
    """Premium POST /api/analytics/ingest → Analytics POST /ingest. No Kafka."""
    correlation_id = request.state.correlation_id
    user_id = user["user_id"]
    tier = user.get("subscription_tier", "free")
    log_with_correlation(correlation_id, "info", "POST /api/analytics/ingest")
    log_with_correlation(
        correlation_id,
        "info",
        f"JWT validated: user_id={user_id}, tier={tier}",
    )
    content = await file.read()
    log_with_correlation(correlation_id, "info", "Calling Analytics Service POST /ingest")
    return await _analytics(
        "POST",
        "/ingest",
        correlation_id=correlation_id,
        data={"user_id": user_id, "subscription_tier": tier, "filename": file.filename or ""},
        files={
            "file": (
                file.filename or "upload",
                content,
                file.content_type or "application/octet-stream",
            )
        },
    )


@router.get("/correlations")
async def correlations(
    request: Request,
    user: Annotated[dict, Depends(rate_limit_analytics_query)],
):
    """Premium correlations. 30 requests per minute."""
    correlation_id = request.state.correlation_id
    log_with_correlation(correlation_id, "info", "GET /api/analytics/correlations")
    return await _analytics(
        "GET",
        "/correlations",
        correlation_id=correlation_id,
        params={"user_id": user["user_id"], "subscription_tier": "premium"},
    )


@router.get("/insights")
async def insights(
    request: Request,
    user: Annotated[dict, Depends(require_premium)],
):
    """Latest LLM narrative for the token user."""
    correlation_id = request.state.correlation_id
    log_with_correlation(correlation_id, "info", "GET /api/analytics/insights")
    return await _analytics(
        "GET",
        "/insights",
        correlation_id=correlation_id,
        params={"user_id": user["user_id"], "subscription_tier": "premium"},
    )


@router.get("/metrics")
async def metrics(
    request: Request,
    user: Annotated[dict, Depends(require_premium)],
):
    """Daily points for the token user."""
    correlation_id = request.state.correlation_id
    log_with_correlation(correlation_id, "info", "GET /api/analytics/metrics")
    return await _analytics(
        "GET",
        "/metrics",
        correlation_id=correlation_id,
        params={"user_id": user["user_id"], "subscription_tier": "premium"},
    )


@router.get("/metrics/{metric_id}")
async def metric_by_id(
    metric_id: str,
    request: Request,
    user: Annotated[dict, Depends(require_premium)],
):
    """Own metric by id. Another user's id is 404."""
    correlation_id = request.state.correlation_id
    log_with_correlation(correlation_id, "info", f"GET /api/analytics/metrics/{metric_id}")
    return await _analytics(
        "GET",
        f"/metrics/{metric_id}",
        correlation_id=correlation_id,
        params={"user_id": user["user_id"], "subscription_tier": "premium"},
    )
