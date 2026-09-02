"""Generate Router — Text completion endpoint.

Matches the contract expected by the API Router:
POST http://llm-service:8003/generate
Body: {"prompt": "...", "user_id": "...", "tier": "premium"}
Response: {"response": "...", "tokens_used": 0}
"""

import asyncio

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from services.llm.providers.resolver import get_provider

router = APIRouter(tags=["generate"])


class GenerateRequest(BaseModel):
    """Generate request schema."""

    prompt: str
    user_id: str
    tier: str = "premium"


class GenerateResponse(BaseModel):
    """Generate response schema."""

    response: str
    tokens_used: int


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    request: Request,
    body: GenerateRequest,
):
    """Generate text completion.

    - **prompt**: The prompt to complete
    - **user_id**: User ID for logging
    - **tier**: Subscription tier (default: premium)
    """
    from services.llm.main import log_with_correlation

    correlation_id = getattr(request.state, "correlation_id", "no-id")

    log_with_correlation(
        correlation_id, "info",
        f"POST /generate — prompt length: {len(body.prompt)} chars, user_id: {body.user_id}",
    )

    try:
        provider = get_provider(body.tier)
    except ValueError as e:
        log_with_correlation(correlation_id, "warning", f"Invalid tier: {body.tier}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    try:
        # Use asyncio.to_thread to avoid blocking the event loop
        response_text = await asyncio.to_thread(provider.complete, body.prompt)
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

    return GenerateResponse(response=response_text, tokens_used=0)