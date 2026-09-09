"""Protected sample endpoints demonstrating JWT and per-user isolation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from apps.api.auth import get_current_user, require_premium
from apps.api.store import User, store

router = APIRouter(prefix="/api", tags=["protected"])


class ProfileResponse(BaseModel):
    user_id: str
    email: str
    subscription_tier: str


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1)


class DocumentResponse(BaseModel):
    document_id: str
    user_id: str
    title: str


@router.get("/profile")
def get_profile(user: User = Depends(get_current_user)) -> ProfileResponse:
    return ProfileResponse(
        user_id=user.user_id,
        email=user.email,
        subscription_tier=user.subscription_tier,
    )


@router.get("/premium/sample")
def premium_sample(user: User = Depends(require_premium)) -> dict[str, str]:
    return {
        "status": "ok",
        "user_id": user.user_id,
        "feature": "premium-sample",
    }


@router.post("/documents", status_code=status.HTTP_201_CREATED)
def create_document(
    body: DocumentCreate,
    user: User = Depends(get_current_user),
) -> DocumentResponse:
    doc = store.add_document(user.user_id, body.title)
    return DocumentResponse(
        document_id=doc.document_id,
        user_id=doc.user_id,
        title=doc.title,
    )


@router.get("/documents")
def list_documents(user: User = Depends(get_current_user)) -> list[DocumentResponse]:
    return [
        DocumentResponse(document_id=doc.document_id, user_id=doc.user_id, title=doc.title)
        for doc in store.list_documents(user.user_id)
    ]


@router.get("/documents/{document_id}")
def get_document(
    document_id: str,
    user: User = Depends(get_current_user),
) -> DocumentResponse:
    doc = store.get_document(document_id)
    if doc is None or doc.user_id != user.user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return DocumentResponse(
        document_id=doc.document_id,
        user_id=doc.user_id,
        title=doc.title,
    )
