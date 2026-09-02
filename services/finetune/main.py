"""Fine-Tune Service — FastAPI Application.

Provides LoRA fine-tuning endpoints for AWS Bedrock.
Handles training job submission and status polling.
"""

import logging

from fastapi import FastAPI, Request

from config import settings

# --- Structured Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(correlation_id)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("finetune-service")


class CorrelationFilter(logging.Filter):
    """Add correlation_id to all log records."""

    def filter(self, record):
        record.correlation_id = getattr(record, "correlation_id", "no-id")
        return True


logger.addFilter(CorrelationFilter())


def log_with_correlation(correlation_id: str, level: str, message: str):
    """Log a message with correlation_id context."""
    extra = {"correlation_id": correlation_id}
    getattr(logger, level)(message, extra=extra)


app = FastAPI(
    title="Fine-Tune Service",
    description="LLM Fine-Tuning — Bedrock training jobs",
    version="0.1.0",
)


# --- Correlation ID Middleware ---
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    """Read correlation ID from X-Request-ID header.

    Do NOT generate a new UUID — the api-router already provides one.
    """
    correlation_id = request.headers.get("X-Request-ID", "no-id")
    request.state.correlation_id = correlation_id

    log_with_correlation(correlation_id, "info", f"{request.method} {request.url.path}")

    response = await call_next(request)
    response.headers["X-Request-ID"] = correlation_id
    return response


# --- Health endpoint ---
@app.get("/health")
async def health_check():
    """Public health check endpoint."""
    import pipeline

    return {
        "status": "ok",
        "service": "finetune-service",
        "active_jobs": pipeline.get_active_jobs_count(),
        "version": "0.1.0",
    }


# --- Import routers ---
from routers import training

app.include_router(training.router)