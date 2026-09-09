"""Chat router — synchronous HTTP to RAG (premium) and LLM.

The router only orchestrates calls. Prompt assembly is a thin facade so the
client hits one endpoint; RAG/LLM own retrieval and generation.
"""

from typing import Annotated

import httpx
from auth import verify_token
from config import get_settings
from fastapi import APIRouter, Depends, HTTPException, Request, status
from logging_setup import log_with_correlation
from pydantic import BaseModel
from rate_limit import rate_limit_chat

router = APIRouter(prefix="/api", tags=["chat"])

EMPTY_CONTEXT = "No relevant context found in your documents."


class ChatRequest(BaseModel):
    """Chat request schema."""

    message: str
    use_rag: bool = True


class ChatResponse(BaseModel):
    """Chat response schema."""

    response: str
    context_used: bool
    sources: list[str] = []
    correlation_id: str


async def _rag_context(
    *,
    message: str,
    user_id: str,
    correlation_id: str,
    rag_url: str,
) -> tuple[str, list[str]]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{rag_url}/context",
            params={"query": message, "user_id": user_id},
            headers={"X-Request-ID": correlation_id},
        )
    if response.status_code != 200:
        return "", []
    data = response.json()
    return data.get("context") or "", data.get("sources") or []


async def _llm_generate(
    *,
    prompt: str,
    user_id: str,
    tier: str,
    correlation_id: str,
    llm_url: str,
) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{llm_url}/generate",
            json={"prompt": prompt, "user_id": user_id, "tier": tier},
            headers={"X-Request-ID": correlation_id},
        )
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM service error",
        )
    return response.json().get("response") or ""


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: Request,
    chat_request: ChatRequest,
    user: Annotated[dict, Depends(verify_token)],
    _: Annotated[dict, Depends(rate_limit_chat)],
):
    """Chat with the LLM, optionally injecting RAG context (premium only)."""
    correlation_id = request.state.correlation_id
    settings = get_settings()
    user_id = user["user_id"]
    tier = user.get("subscription_tier", "free")

    log_with_correlation(correlation_id, "info", "POST /api/chat")
    log_with_correlation(
        correlation_id,
        "info",
        f"JWT validated: user_id={user_id}, tier={tier}",
    )

    context = ""
    sources: list[str] = []
    context_used = False

    if chat_request.use_rag and tier == "premium":
        log_with_correlation(correlation_id, "info", "Calling RAG Service for context")
        try:
            context, sources = await _rag_context(
                message=chat_request.message,
                user_id=user_id,
                correlation_id=correlation_id,
                rag_url=settings.RAG_SERVICE_URL,
            )
            if context and context != EMPTY_CONTEXT:
                context_used = True
                log_with_correlation(
                    correlation_id,
                    "info",
                    f"RAG context received: {len(sources)} sources",
                )
        except httpx.HTTPError as exc:
            log_with_correlation(
                correlation_id,
                "warning",
                f"RAG service unavailable, continuing without context: {exc}",
            )

    prompt = (
        f"Based on the following context from the user's documents:\n\n{context}\n\n"
        f"Answer the user's question: {chat_request.message}"
        if context_used
        else chat_request.message
    )

    log_with_correlation(correlation_id, "info", "Calling LLM Service for response")
    try:
        response_text = await _llm_generate(
            prompt=prompt,
            user_id=user_id,
            tier=tier,
            correlation_id=correlation_id,
            llm_url=settings.LLM_SERVICE_URL,
        )
    except httpx.TimeoutException as exc:
        log_with_correlation(correlation_id, "error", "LLM service timeout")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="LLM service timeout",
        ) from exc
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "error", f"Error calling LLM service: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error calling LLM service: {exc}",
        ) from exc

    log_with_correlation(correlation_id, "info", "LLM response received")
    log_with_correlation(correlation_id, "info", "Response: 200 OK")

    return ChatResponse(
        response=response_text,
        context_used=context_used,
        sources=sources,
        correlation_id=correlation_id,
    )
