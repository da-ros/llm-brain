"""Health router — public, no JWT."""

from config import get_settings
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Public health check. Spec requires service name api-gateway and version."""
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION,
    }
