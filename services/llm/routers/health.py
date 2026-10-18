"""Health router — public, no auth."""

from config import get_settings
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Public health check for the local LLM process (real backend + provider)."""
    settings = get_settings()
    backend = (settings.LLM_BACKEND or "qwen_local").strip().lower()
    if settings.QWEN_MOCK:
        provider = "mock"
    elif backend in {"ollama", "ollama_local"}:
        provider = "ollama"
    else:
        provider = "qwen-local"
    return {
        "status": "ok",
        "service": settings.SERVICE_NAME,
        "backend": backend,
        "provider": provider,
        "device": settings.QWEN_DEVICE,
        "model": settings.OLLAMA_MODEL if provider == "ollama" else settings.QWEN_MODEL_ID,
        "version": settings.SERVICE_VERSION,
    }
