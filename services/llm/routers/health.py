"""Health router — public, no auth."""

from config import get_settings
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Public health check for the local Qwen3.5-4B process."""
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.SERVICE_NAME,
        "provider": "qwen-local",
        "device": settings.QWEN_DEVICE,
        "model": settings.QWEN_MODEL_ID,
        "version": settings.SERVICE_VERSION,
    }
