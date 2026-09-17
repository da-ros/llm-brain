"""Chat router — premium via Agents Razonador; free skips agents and Kafka.

CHAT_VIA_AGENTS=false restores the previous Router → RAG → LLM path (rollback).
"""

from typing import Annotated

import httpx
from auth import verify_token
from config import get_settings
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from kafka_io import publish_session_turn_completed
from logging_setup import log_with_correlation
from pydantic import BaseModel
from rate_limit import rate_limit_chat

router = APIRouter(prefix="/api", tags=["chat"])

EMPTY_CONTEXT = "No relevant context found in your documents."


class ChatRequest(BaseModel):
    """Chat request schema."""

    message: str
    use_rag: bool = True
    session_id: str | None = None


class ChatResponse(BaseModel):
    """Chat response schema."""

    response: str
    context_used: bool
    sources: list[str] = []
    assumptions: list[str] = []
    tokens_used: int = 0
    session_id: str | None = None
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


async def _agents_reason(
    *,
    message: str,
    user_id: str,
    session_id: str | None,
    correlation_id: str,
    agents_url: str,
) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{agents_url}/reason",
            json={
                "user_id": user_id,
                "subscription_tier": "premium",
                "message": message,
                "session_id": session_id,
            },
            headers={"X-Request-ID": correlation_id},
        )
    if response.status_code == status.HTTP_504_GATEWAY_TIMEOUT:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="LLM service timeout",
        )
    if response.status_code >= 500:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Agents service error",
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail="Agents service error")
    return response.json()


def _publish_turn(payload: dict) -> None:
    try:
        publish_session_turn_completed(payload)
    except Exception as exc:
        log_with_correlation(
            payload.get("correlation_id", "no-id"),
            "warning",
            f"Kafka session.turn.completed skipped: {exc}",
        )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: Request,
    chat_request: ChatRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[dict, Depends(verify_token)],
    _: Annotated[dict, Depends(rate_limit_chat)],
):
    """Premium chat uses Razonador. Free chat skips agents, RAG, and Kafka."""
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

    if tier == "premium" and settings.CHAT_VIA_AGENTS:
        log_with_correlation(correlation_id, "info", "Calling Agents Service POST /reason")
        try:
            data = await _agents_reason(
                message=chat_request.message,
                user_id=user_id,
                session_id=chat_request.session_id,
                correlation_id=correlation_id,
                agents_url=settings.AGENTS_SERVICE_URL,
            )
        except httpx.TimeoutException as exc:
            log_with_correlation(correlation_id, "error", "Agents service timeout")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Agents service timeout",
            ) from exc
        except HTTPException:
            raise
        except httpx.HTTPError as exc:
            log_with_correlation(correlation_id, "error", f"Error calling Agents service: {exc}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Error calling Agents service: {exc}",
            ) from exc

        response_text = data.get("response") or ""
        sources = data.get("sources") or []
        assumptions = data.get("assumptions") or []
        session_id = data.get("session_id") or chat_request.session_id
        tokens_used = int(data.get("tokens_used") or 0)
        background_tasks.add_task(
            _publish_turn,
            {
                "correlation_id": correlation_id,
                "user_id": user_id,
                "session_id": session_id,
                "query": chat_request.message,
                "response": response_text,
                "assumptions": assumptions,
                "sources": sources,
            },
        )
        log_with_correlation(correlation_id, "info", "Response: 200 OK (Razonador)")
        return ChatResponse(
            response=response_text,
            context_used=bool(sources),
            sources=sources,
            assumptions=assumptions,
            tokens_used=tokens_used,
            session_id=session_id,
            correlation_id=correlation_id,
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
        assumptions=[],
        tokens_used=0,
        session_id=chat_request.session_id,
        correlation_id=correlation_id,
    )
