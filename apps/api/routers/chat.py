"""Chat Router — LLM chat endpoint with RAG context injection.

Provides chat functionality with optional RAG context for premium users.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from apps.api.config import settings
from apps.api.llm.resolver import get_provider
from apps.api.main import verify_token
from services.rag.rag_service import rag_service

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


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user: Annotated[dict, Depends(verify_token)],
):
    """Chat with LLM, optionally using RAG context.

    - **message**: User's question
    - **use_rag**: Whether to use RAG context (default: true)
    - Requires valid JWT token
    - RAG context only for premium tier
    """
    user_id = user["user_id"]
    tier = user.get("subscription_tier", "free")

    context = ""
    sources = []
    context_used = False

    # RAG context only for premium users
    if request.use_rag and tier == "premium":
        try:
            context = await rag_service.context_injection(request.message, user_id)
            if context and context != "No relevant context found in your documents.":
                context_used = True
                # Extract sources from context
                sources = [
                    line.split("(source: ")[-1].rstrip(")")
                    for line in context.split("\n")
                    if "(source:" in line
                ]
        except Exception:
            pass  # Gracefully degrade without RAG

    # Build prompt
    if context_used:
        prompt = f"""Based on the following context from the user's documents:

{context}

Answer the user's question: {request.message}"""
    else:
        prompt = request.message

    # Get LLM response
    try:
        provider = get_provider(tier)
        response = provider.complete(prompt)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM error: {str(e)}",
        )

    return ChatResponse(
        response=response,
        context_used=context_used,
        sources=sources,
    )
