"""Premium shield routes. Sync HTTP to Shield Service. No Kafka."""

from typing import Annotated, Any

import httpx
from auth import require_premium
from config import get_settings
from fastapi import APIRouter, Depends, HTTPException, Request, status
from logging_setup import log_with_correlation
from pydantic import BaseModel
from rate_limit import rate_limit_shield

router = APIRouter(prefix="/api/shield", tags=["shield"])


class ScanRequest(BaseModel):
    """Client scan payload. user_id comes from the JWT, not the body."""

    text: str = ""
    source: str = ""
    filename: str = ""
    content_base64: str = ""


async def _shield(
    method: str,
    path: str,
    *,
    correlation_id: str,
    json_body: dict | None = None,
    params: dict | None = None,
) -> Any:
    settings = get_settings()
    url = f"{settings.SHIELD_SERVICE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method,
                url,
                json=json_body,
                params=params,
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.TimeoutException as exc:
        log_with_correlation(correlation_id, "error", "Shield service timeout")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Shield service timeout",
        ) from exc
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "error", f"Error calling Shield service: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error calling Shield service: {exc}",
        ) from exc

    if response.status_code == status.HTTP_504_GATEWAY_TIMEOUT:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Shield service timeout",
        )
    if response.status_code >= 500:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Shield service error",
        )
    if response.status_code >= 400:
        detail = "Shield service error"
        try:
            detail = (response.json() or {}).get("detail") or detail
        except Exception:
            detail = response.text or detail
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


@router.post("/scan")
async def scan(
    request: Request,
    body: ScanRequest,
    user: Annotated[dict, Depends(rate_limit_shield)],
):
    """Premium POST /api/shield/scan → Shield POST /scan. Does not publish Kafka."""
    correlation_id = request.state.correlation_id
    user_id = user["user_id"]
    tier = user.get("subscription_tier", "free")
    log_with_correlation(correlation_id, "info", "POST /api/shield/scan")
    log_with_correlation(
        correlation_id,
        "info",
        f"JWT validated: user_id={user_id}, tier={tier}",
    )
    source = (body.source or "").strip().lower()
    text = (body.text or "").strip()
    if source not in {"email", "sms", "message", "image", "video"} or (
        not text and not body.content_base64
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="text or file is required, and source must be valid",
        )
    log_with_correlation(correlation_id, "info", "Calling Shield Service POST /scan")
    return await _shield(
        "POST",
        "/scan",
        correlation_id=correlation_id,
        json_body={
            "user_id": user_id,
            "subscription_tier": tier,
            "source": source,
            "text": body.text,
            "filename": body.filename,
            "content_base64": body.content_base64,
        },
    )


@router.get("/incidents")
async def list_incidents(
    request: Request,
    user: Annotated[dict, Depends(require_premium)],
):
    """Premium list. Frame 7 shape. Empty list is 200."""
    correlation_id = request.state.correlation_id
    log_with_correlation(correlation_id, "info", "GET /api/shield/incidents")
    return await _shield(
        "GET",
        "/incidents",
        correlation_id=correlation_id,
        params={"user_id": user["user_id"], "subscription_tier": "premium"},
    )


@router.get("/guidelines")
async def guidelines(
    request: Request,
    user: Annotated[dict, Depends(require_premium)],
):
    """Premium responsible-use text."""
    correlation_id = request.state.correlation_id
    log_with_correlation(correlation_id, "info", "GET /api/shield/guidelines")
    return await _shield(
        "GET",
        "/guidelines",
        correlation_id=correlation_id,
        params={"user_id": user["user_id"], "subscription_tier": "premium"},
    )
