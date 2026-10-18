"""LLM Service — FastAPI application.

Local Qwen3.5-4B base inference for web free, premium, and ETL triple extraction.
Backend per machine: qwen_local (in-process, Mac/Metal) or ollama (Linux).
"""

from __future__ import annotations

from config import get_settings
from fastapi import FastAPI, Request
from logging_setup import correlation_id_var, log_with_correlation, logger
from routers import chat, extract, generate, health


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
        title="LLM Service",
        description=(
            "Local Qwen3.5-4B base inference — qwen_local (Metal) or ollama "
            "(Linux); web free, premium, and ETL"
        ),
        version=settings.SERVICE_VERSION,
    )
    application.middleware("http")(add_correlation_id)
    application.include_router(health.router)
    application.include_router(generate.router)
    application.include_router(chat.router)
    application.include_router(extract.router)
    logger.info(
        "LLM Service ready — backend=%s model=%s mock=%s",
        settings.LLM_BACKEND,
        settings.OLLAMA_MODEL if "ollama" in settings.LLM_BACKEND else settings.QWEN_MODEL_ID,
        settings.QWEN_MOCK,
    )
    return application


app = create_app()
