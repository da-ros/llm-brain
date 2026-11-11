"""Fine-Tune Service — FastAPI application.

Local LoRA over Qwen3.5-4B. Manual trigger only (POST /train).
"""

from __future__ import annotations

from config import get_settings
from fastapi import FastAPI, Request
from logging_setup import correlation_id_var, log_with_correlation, logger
from routers import health, publish, training


async def add_correlation_id(request: Request, call_next):
    """Propagate X-Request-ID from the API Router. Do not mint a new UUID."""
    correlation_id = request.headers.get("X-Request-ID", "no-id")
    request.state.correlation_id = correlation_id
    token = correlation_id_var.set(correlation_id)
    log_with_correlation(correlation_id, "info", f"{request.method} {request.url.path}")
    try:
        response = await call_next(request)
    finally:
        correlation_id_var.reset(token)
    response.headers["X-Request-ID"] = correlation_id
    return response


def create_app() -> FastAPI:
    """Build the FastAPI application (used by tests and uvicorn)."""
    settings = get_settings()
    application = FastAPI(
        title="Fine-Tune Service",
        description="Local LoRA fine-tuning over Qwen3.5-4B (PEFT / ms-swift / Unsloth)",
        version=settings.SERVICE_VERSION,
    )
    application.middleware("http")(add_correlation_id)
    application.include_router(health.router)
    application.include_router(training.router)
    application.include_router(publish.router)
    logger.info(
        "Fine-Tune Service ready — backend=%s model=%s",
        settings.LORA_BACKEND,
        settings.BASE_MODEL_ID,
    )
    return application


app = create_app()
