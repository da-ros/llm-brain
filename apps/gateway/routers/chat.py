"""Chat Router — Synchronous chat with RAG context injection.

Handles chat requests synchronously via HTTP to RAG and LLM services.
"""

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from config import settings
from main import verify_token

router = APIRouter(prefix="/api", tags=["chat"])


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


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: Request,
    chat_request: ChatRequest,
    user: Annotated[dict, Depends(verify_token)],
):
    """Chat with LLM, optionally using RAG context.

    Synchronous: calls RAG and LLM services via HTTP.
    """
    correlation_id = request.state.correlation_id
    user_id = user["user_id"]
    tier = user.get("subscription_tier", "free")

    context = ""
    sources = []
    context_used = False

    # RAG context only for premium users
    if chat_request.use_rag and tier == "premium":
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                rag_response = await client.get(
                    f"http://rag-service:8002/context",
                    params={"query": chat_request.message, "user_id": user_id},
                    headers={"X-Request-ID": correlation_id},
                )
                if rag_response.status_code == 200:
                    rag_data = rag_response.json()
                    context = rag_data.get("context", "")
                    sources = rag_data.get("sources", [])
                    if context and context != "No relevant context found in your documents.":
                        context_used = True
        except Exception:
            pass  # Gracefully degrade without RAG

    # Build prompt
    if context_used:
        prompt = f"""Based on the following context from the user's documents:

{context}

Answer the user's question: {chat_request.message}"""
    else:
        prompt = chat_request.message

    # Call LLM service
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            llm_response = await client.post(
                "http://llm-service:8003/generate",
                json={"prompt": prompt, "user_id": user_id, "tier": tier},
                headers={"X-Request-ID": correlation_id},
            )
            if llm_response.status_code == 200:
                llm_data = llm_response.json()
                response_text = llm_data.get("response", "")
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="LLM service error",
                )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="LLM service timeout",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calling LLM service: {str(e)}",
        )

    return ChatResponse(
        response=response_text,
        context_used=context_used,
        sources=sources,
        correlation_id=correlation_id,
    )
