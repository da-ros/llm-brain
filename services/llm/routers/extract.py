"""POST /extract — ETL triple extraction via the base Qwen3.5-4B model."""

from __future__ import annotations

import asyncio
from typing import Any

from config import get_settings
from exceptions import InferenceTimeoutError, ModelNotFoundError, ModelUnavailableError
from fastapi import APIRouter, HTTPException, Request, status
from logging_setup import log_with_correlation
from providers.resolver import get_provider
from pydantic import BaseModel

router = APIRouter(tags=["extract"])


class ExtractRequest(BaseModel):
    """Extract request schema."""

    content: str | None = None
    user_id: str | None = None
    tier: str = "premium"


class ExtractResponse(BaseModel):
    """Extract response schema."""

    triples: list[dict[str, Any]]
    tokens_used: int


@router.post("/extract", response_model=ExtractResponse)
async def extract(request: Request, body: ExtractRequest):
    """Reason over document content and return SPO triples (Frame 2 ETL)."""
    correlation_id = getattr(request.state, "correlation_id", "no-id")
    settings = get_settings()

    if not body.content or not body.content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request (missing content)",
        )

    log_with_correlation(
        correlation_id,
        "info",
        f"POST /extract — content length: {len(body.content)} chars",
    )

    try:
        provider = get_provider(body.tier)
    except ValueError as exc:
        log_with_correlation(correlation_id, "warning", f"Invalid tier: {body.tier}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not hasattr(provider, "extract_triples"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Triple extraction requires a provider with extract_triples",
        )

    try:
        triples, tokens_used = await asyncio.wait_for(
            asyncio.to_thread(provider.extract_triples, body.content),
            timeout=settings.INFERENCE_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        log_with_correlation(correlation_id, "error", "Qwen3.5-4B inference timeout")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Inference timeout",
        ) from exc
    except InferenceTimeoutError as exc:
        log_with_correlation(correlation_id, "error", str(exc))
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Inference timeout",
        ) from exc
    except (ModelUnavailableError, ModelNotFoundError) as exc:
        log_with_correlation(correlation_id, "error", f"Qwen3.5-4B container/model error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        log_with_correlation(correlation_id, "error", f"LLM error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference error: {exc}",
        ) from exc

    log_with_correlation(
        correlation_id,
        "info",
        f"Qwen3.5-4B triples: {len(triples)} items, {tokens_used} tokens",
    )
    return ExtractResponse(triples=triples, tokens_used=tokens_used)
