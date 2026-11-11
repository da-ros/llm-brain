"""Premium what-if routes. Sync HTTP to Simulator Service. No Kafka."""

from typing import Annotated, Any

import httpx
from auth import require_premium
from config import get_settings
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from logging_setup import log_with_correlation
from pydantic import BaseModel
from rate_limit import rate_limit_simulate

router = APIRouter(prefix="/api", tags=["simulate"])


class SimulateRequest(BaseModel):
    """Client what-if payload. user_id comes from the JWT, not the body."""

    question: str = ""
    variables: dict[str, Any] | None = None


async def _simulator(
    method: str,
    path: str,
    *,
    correlation_id: str,
    json_body: dict | None = None,
    params: dict | None = None,
    timeout: float = 30.0,
) -> Any:
    settings = get_settings()
    url = f"{settings.SIMULATOR_SERVICE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method,
                url,
                json=json_body,
                params=params,
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.TimeoutException as exc:
        log_with_correlation(correlation_id, "error", "Simulator service timeout")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Simulator service timeout",
        ) from exc
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "error", f"Error calling Simulator service: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error calling Simulator service: {exc}",
        ) from exc

    if response.status_code == status.HTTP_504_GATEWAY_TIMEOUT:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Simulator service timeout",
        )
    if response.status_code >= 500:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Simulator service error",
        )
    if response.status_code == status.HTTP_204_NO_CONTENT:
        return None
    if response.status_code >= 400:
        detail = "Simulator service error"
        try:
            detail = (response.json() or {}).get("detail") or detail
        except Exception:
            detail = response.text or detail
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


@router.post("/simulate")
async def simulate(
    request: Request,
    body: SimulateRequest,
    user: Annotated[dict, Depends(rate_limit_simulate)],
):
    """Premium POST /api/simulate → Simulator POST /simulate. Does not publish Kafka."""
    correlation_id = request.state.correlation_id
    user_id = user["user_id"]
    tier = user.get("subscription_tier", "free")
    log_with_correlation(correlation_id, "info", "POST /api/simulate")
    log_with_correlation(
        correlation_id,
        "info",
        f"JWT validated: user_id={user_id}, tier={tier}",
    )
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="question is required",
        )
    log_with_correlation(correlation_id, "info", "Calling Simulator Service POST /simulate")
    settings = get_settings()
    return await _simulator(
        "POST",
        "/simulate",
        correlation_id=correlation_id,
        timeout=settings.INFERENCE_TIMEOUT_SECONDS,
        json_body={
            "user_id": user_id,
            "subscription_tier": tier,
            "question": question,
            "variables": body.variables,
        },
    )


@router.get("/simulations")
async def list_simulations(
    request: Request,
    user: Annotated[dict, Depends(require_premium)],
):
    """Premium history. Only the token user's rows come back from Simulator."""
    correlation_id = request.state.correlation_id
    log_with_correlation(correlation_id, "info", "GET /api/simulations")
    return await _simulator(
        "GET",
        "/simulations",
        correlation_id=correlation_id,
        params={"user_id": user["user_id"], "subscription_tier": "premium"},
    )


@router.get("/simulations/{simulation_id}")
async def get_simulation(
    simulation_id: str,
    request: Request,
    user: Annotated[dict, Depends(require_premium)],
):
    """Premium fetch. Cross-user ids are 404 from Simulator and are forwarded."""
    correlation_id = request.state.correlation_id
    log_with_correlation(
        correlation_id,
        "info",
        f"GET /api/simulations/{simulation_id}",
    )
    return await _simulator(
        "GET",
        f"/simulations/{simulation_id}",
        correlation_id=correlation_id,
        params={"user_id": user["user_id"], "subscription_tier": "premium"},
    )


@router.delete(
    "/simulations/{simulation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_simulation(
    simulation_id: str,
    request: Request,
    user: Annotated[dict, Depends(require_premium)],
):
    """Premium delete. Another user's id is 404 from Simulator and is forwarded."""
    correlation_id = request.state.correlation_id
    log_with_correlation(
        correlation_id,
        "info",
        f"DELETE /api/simulations/{simulation_id}",
    )
    await _simulator(
        "DELETE",
        f"/simulations/{simulation_id}",
        correlation_id=correlation_id,
        params={"user_id": user["user_id"], "subscription_tier": "premium"},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
