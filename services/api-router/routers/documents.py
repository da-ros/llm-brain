"""Documents router — JWT-scoped list/get via the RAG service.

Wrong-user and missing documents are HTTP 404 (never reveal existence).
"""

from typing import Annotated

import httpx
from auth import verify_token
from config import get_settings
from fastapi import APIRouter, Depends, HTTPException, Request, status
from logging_setup import log_with_correlation

router = APIRouter(prefix="/api", tags=["documents"])


@router.get("/documents")
async def list_documents(
    request: Request,
    user: Annotated[dict, Depends(verify_token)],
):
    """List the caller's documents only."""
    correlation_id = request.state.correlation_id
    settings = get_settings()
    log_with_correlation(correlation_id, "info", "GET /api/documents")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.RAG_SERVICE_URL}/documents",
                params={"user_id": user["user_id"]},
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"RAG service error: {exc}",
        ) from exc
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="RAG service error",
        )
    return response.json()


@router.get("/documents/{doc_id}")
async def get_document(
    request: Request,
    doc_id: str,
    user: Annotated[dict, Depends(verify_token)],
):
    """Fetch one document owned by the caller. Otherwise 404."""
    correlation_id = request.state.correlation_id
    settings = get_settings()
    log_with_correlation(correlation_id, "info", f"GET /api/documents/{doc_id}")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.RAG_SERVICE_URL}/documents/{doc_id}",
                params={"user_id": user["user_id"]},
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"RAG service error: {exc}",
        ) from exc
    if response.status_code == 404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="RAG service error",
        )
    return response.json()
