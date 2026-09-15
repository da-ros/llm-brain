"""Health router — public, no auth."""

import pipeline
from config import get_settings
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Public health check with active job count."""
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.SERVICE_NAME,
        "active_jobs": pipeline.get_active_jobs_count(),
        "version": settings.SERVICE_VERSION,
    }
