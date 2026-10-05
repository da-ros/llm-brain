"""POST /generate — text completion with local Qwen3.5-4B.

Optional media is the image or short-video bytes themselves, used when OCR
found no text. The route does not log those bytes.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Literal

from config import get_settings
from exceptions import InferenceTimeoutError, ModelNotFoundError, ModelUnavailableError
from fastapi import APIRouter, HTTPException, Request, status
from logging_setup import log_with_correlation
from providers.resolver import get_provider
from pydantic import BaseModel, Field

router = APIRouter(tags=["generate"])


class MediaPart(BaseModel):
    """One image or short clip. content_base64 is the file itself."""

    kind: Literal["image", "video"]
    filename: str = ""
    content_base64: str


class GenerateRequest(BaseModel):
    """Generate request schema."""

    prompt: str | None = None
    user_id: str | None = None
    tier: str = "premium"
    media: list[MediaPart] = Field(default_factory=list)


class GenerateResponse(BaseModel):
    """Generate response schema."""

    response: str
    tokens_used: int


@router.post("/generate", response_model=GenerateResponse)
async def generate(request: Request, body: GenerateRequest):
    """Run text completion on the base Qwen3.5-4B container."""
    correlation_id = getattr(request.state, "correlation_id", "no-id")
    settings = get_settings()

    if not body.prompt or not body.prompt.strip():
        log_with_correlation(correlation_id, "warning", "POST /generate — missing prompt")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request (missing prompt)",
        )
    if not body.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request (missing user_id)",
        )

    media: list[tuple[str, bytes, str]] = []
    for part in body.media:
        try:
            payload = base64.b64decode(part.content_base64, validate=True)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid request (media is not valid base64)",
            ) from exc
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid request (empty media)",
            )
        media.append((part.kind, payload, part.filename))

    log_with_correlation(
        correlation_id,
        "info",
        f"POST /generate — prompt length: {len(body.prompt)} chars, media: {len(media)}",
    )

    try:
        provider = get_provider(body.tier)
    except ValueError as exc:
        log_with_correlation(correlation_id, "warning", f"Invalid tier: {body.tier}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        call = (
            asyncio.to_thread(provider.complete, body.prompt, media)
            if media
            else asyncio.to_thread(provider.complete, body.prompt)
        )
        result = await asyncio.wait_for(call, timeout=settings.INFERENCE_TIMEOUT_SECONDS)
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
        f"Qwen3.5-4B response: {result.tokens_used} tokens",
    )
    return GenerateResponse(response=result.text, tokens_used=result.tokens_used)
