"""FastAPI Application.

Main application entry point with router mounting structure.
"""

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from apps.api.config import settings
from apps.api.routers import chat, upload

app = FastAPI(
    title="llm-brain API",
    description="AI-Augmented Digital Brain — Multi-tenant personal knowledge management",
    version="0.1.0",
)

# Mount routers
app.include_router(upload.router)
app.include_router(chat.router)

# Security scheme for JWT
security = HTTPBearer()


# --- Health endpoint (public) ---
@app.get("/health")
async def health_check():
    """Public health check endpoint.

    Returns service status and resolved LLM provider.
    No secrets are exposed.
    """
    return {
        "status": "ok",
        "llm_provider": settings.LLM_PROVIDER,
        "version": "0.1.0",
    }


# --- Auth dependency (JWT) ---
def verify_token(credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]):
    """Verify JWT token and return user info.

    This dependency is used to protect endpoints.
    """
    from jose import jwt, JWTError

    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID",
            )
        return {"user_id": user_id, "subscription_tier": payload.get("tier", "free")}
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
        )


# --- Protected endpoint (example) ---
@app.get("/api/profile")
async def get_profile(user: Annotated[dict, Depends(verify_token)]):
    """Protected endpoint example.

    Requires a valid JWT token.
    """
    return {
        "user_id": user["user_id"],
        "subscription_tier": user["subscription_tier"],
    }
