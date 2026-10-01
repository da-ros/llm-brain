"""Premium-only access and per-user isolation helpers."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status


def ensure_premium(tier: str | None) -> None:
    """Reject anyone who is not premium (HTTP 403)."""
    if (tier or "free") != "premium":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Premium subscription required",
        )


def owned_or_404(document: dict[str, Any] | None, user_id: str) -> dict[str, Any]:
    """Return the document only when it belongs to user_id."""
    if document is None or document.get("user_id") != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return document
