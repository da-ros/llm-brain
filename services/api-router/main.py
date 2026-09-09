"""API Router — FastAPI application.

Central entry point for client requests: JWT, correlation ID, rate limiting,
routing to RAG/LLM over HTTP, and Kafka for async file uploads.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import db
import kafka_io
from config import get_settings
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from logging_setup import correlation_id_var, log_with_correlation, logger
from routers import chat, health, tasks, upload


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect MongoDB, ensure TTL index, start Kafka consumer."""
    settings = get_settings()
    await db.connect()
    await db.ensure_indexes()
    if settings.KAFKA_ENABLED:
        kafka_io.start_consumer_thread()
    else:
        logger.info("Kafka consumer disabled (KAFKA_ENABLED=false)")
    yield
    kafka_io.stop_consumer_thread()
    await db.disconnect()


async def add_correlation_id(request: Request, call_next):
    """Generate or propagate X-Request-ID on every request."""
    correlation_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
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
        title="llm-brain API Router",
        description="AI-Augmented Digital Brain — API Router (gateway)",
        version=settings.SERVICE_VERSION,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.middleware("http")(add_correlation_id)
    application.include_router(health.router)
    application.include_router(upload.router)
    application.include_router(chat.router)
    application.include_router(tasks.router)
    return application


app = create_app()
