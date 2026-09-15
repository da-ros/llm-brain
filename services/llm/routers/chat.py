"""POST /chat — multimodal chat with optional RAG context."""

from __future__ import annotations

import asyncio
from typing import Any

from config import get_settings
from exceptions import InferenceTimeoutError, ModelNotFoundError, ModelUnavailableError
from fastapi import APIRouter, HTTPException, Request, status
from logging_setup import log_with_correlation
from providers.resolver import get_provider
from pydantic import BaseModel

router = APIRouter(tags=["chat"])


class ChatMessage(BaseModel):
    """Chat message — content may be text or multimodal parts."""

    role: str
    content: str | list[dict[str, Any]]


class ChatRequest(BaseModel):
    """Chat request schema."""

    messages: list[ChatMessage] | None = None
    user_id: str | None = None
    tier: str = "premium"
    context: str | None = None


class ChatResponse(BaseModel):
    """Chat response schema."""

    response: str
    tokens_used: int


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    """Run multimodal chat on the base Qwen3.5-4B container."""
    correlation_id = getattr(request.state, "correlation_id", "no-id")
    settings = get_settings()

    if not body.messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request (missing messages)",
        )
    if not body.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request (missing user_id)",
        )

    log_with_correlation(
        correlation_id,
        "info",
        f"POST /chat — messages: {len(body.messages)}, user_id: {body.user_id}",
    )

    try:
        provider = get_provider(body.tier)
    except ValueError as exc:
        log_with_correlation(correlation_id, "warning", f"Invalid tier: {body.tier}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    messages_list = [msg.model_dump() for msg in body.messages]

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(provider.chat, messages_list, body.context),
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
        f"Qwen3.5-4B response: {result.tokens_used} tokens",
    )
    return ChatResponse(response=result.text, tokens_used=result.tokens_used)
