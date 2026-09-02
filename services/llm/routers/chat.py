"""Chat Router — Multi-turn chat endpoint.

Provides chat functionality with optional RAG context.
"""

import asyncio

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from services.llm.providers.resolver import get_provider

router = APIRouter(tags=["chat"])


class ChatMessage(BaseModel):
    """Chat message schema."""

    role: str
    content: str


class ChatRequest(BaseModel):
    """Chat request schema."""

    messages: list[ChatMessage]
    user_id: str
    tier: str = "premium"
    context: str | None = None


class ChatResponse(BaseModel):
    """Chat response schema."""

    response: str
    tokens_used: int


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: Request,
    body: ChatRequest,
):
    """Chat with LLM, optionally using RAG context.

    - **messages**: List of messages (role, content)
    - **user_id**: User ID for logging
    - **tier**: Subscription tier (default: premium)
    - **context**: Optional RAG context
    """
    from services.llm.main import log_with_correlation

    correlation_id = getattr(request.state, "correlation_id", "no-id")

    log_with_correlation(
        correlation_id, "info",
        f"POST /chat — messages: {len(body.messages)}, user_id: {body.user_id}",
    )

    try:
        provider = get_provider(body.tier)
    except ValueError as e:
        log_with_correlation(correlation_id, "warning", f"Invalid tier: {body.tier}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    messages_list = [msg.model_dump() for msg in body.messages]

    try:
        # Use asyncio.to_thread to avoid blocking the event loop
        response_text = await asyncio.to_thread(provider.chat, messages_list, body.context)
    except Exception as e:
        log_with_correlation(correlation_id, "error", f"LLM error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM error: {str(e)}",
        )

    log_with_correlation(
        correlation_id, "info",
        f"Response: 200 OK — tokens_used: 0",
    )

    return ChatResponse(response=response_text, tokens_used=0)