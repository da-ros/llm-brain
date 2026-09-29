"""JWT verification for protected API Router endpoints.

The router validates tokens at the edge. Downstream services trust this
result — there is no service-to-service JWT in the MVP.
"""

from typing import Annotated

from config import get_settings
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, decode
from jwt import PyJWTError as JWTError
from logging_setup import log_with_correlation

security = HTTPBearer(auto_error=False)


def _correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", "no-id")


def verify_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> dict:
    """Decode the bearer token and return user_id + subscription_tier."""
    correlation_id = _correlation_id(request)
    if credentials is None:
        log_with_correlation(correlation_id, "warning", "JWT validation failed: missing token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    settings = get_settings()
    try:
        payload = decode(
            credentials.credentials,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except ExpiredSignatureError as exc:
        log_with_correlation(correlation_id, "warning", "JWT validation failed: Token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        ) from exc
    except JWTError as exc:
        log_with_correlation(correlation_id, "warning", "JWT validation failed: Invalid token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc

    user_id = payload.get("sub")
    if not user_id:
        log_with_correlation(correlation_id, "warning", "JWT validation failed: missing user ID")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing user ID",
        )

    tier = payload.get("subscription_tier") or payload.get("tier") or "free"
    log_with_correlation(
        correlation_id,
        "debug",
        f"JWT validated: user_id={user_id}, tier={tier}",
    )
    return {"user_id": user_id, "subscription_tier": tier}


def require_premium(user: Annotated[dict, Depends(verify_token)]) -> dict:
    """Reject Free-tier callers on Premium-only endpoints (upload, RAG)."""
    if user.get("subscription_tier") != "premium":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Premium subscription required",
        )
    return user
