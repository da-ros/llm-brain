"""ETL Service — FastAPI application.

Standalone memory-distillation microservice on port 8001.
No upload HTTP endpoint (API Router owns POST /api/upload). Health stays 200
regardless of Kafka / distillation activity.
"""

from __future__ import annotations

from config import get_settings
from fastapi import FastAPI, Request
from logging_setup import correlation_id_var, log_with_correlation, logger


async def add_correlation_id(request: Request, call_next):
    """Propagate X-Request-ID. Do not mint a new UUID."""
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
        title="ETL Service",
        description="One-Tap Memory Distillation — LangChain loaders + LLM triples",
        version=settings.SERVICE_VERSION,
    )
    application.middleware("http")(add_correlation_id)

    @application.get("/health")
    async def health_check():
        return {
            "status": "ok",
            "service": settings.SERVICE_NAME,
            "version": settings.SERVICE_VERSION,
        }

    @application.on_event("startup")
    async def startup_event():
        if not settings.KAFKA_ENABLED:
            logger.info("Kafka consumer disabled (KAFKA_ENABLED=false)")
            return
        from kafka_io import start_consumer_thread

        start_consumer_thread()

    logger.info("ETL Service ready — port=%s llm=%s", settings.API_PORT, settings.LLM_SERVICE_URL)
    return application


app = create_app()
