"""Public health probe."""

from fastapi import APIRouter

from apps.api.config import get_settings

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. Never includes secrets."""
    settings = get_settings()
    return {
        "status": "ok",
        "llm_provider": settings.canonical_llm_provider(),
    }
