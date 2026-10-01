"""Analytics Service — FastAPI application on port 8008.

Clients never call this port. The API Router is the facade. Ingest is
synchronous HTTP: LangChain load, RAG excerpts, one LLM call, Pearson.
No Kafka and no Google OAuth.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import db
import pipeline
from base import ensure_premium, owned_or_404
from config import get_settings
from exceptions import EmptyFileError, LLMTimeoutError, LLMUpstreamError, UnsupportedFileError
from fastapi import FastAPI, HTTPException, Request, status
from logging_setup import correlation_id_var, log_with_correlation, logger


async def add_correlation_id(request: Request, call_next):
    """Propagate X-Request-ID, or mint a UUID when the inbound header is missing."""
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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        await db.connect()
        await db.ensure_indexes()
    except Exception:
        logger.exception("MongoDB connection failed at startup (health still 200)")
    yield
    await db.disconnect()


def _tier(request: Request, explicit: str | None) -> str:
    return explicit or request.headers.get("X-Subscription-Tier") or "free"


def create_app() -> FastAPI:
    """Build the FastAPI application (used by tests and uvicorn)."""
    settings = get_settings()
    application = FastAPI(
        title="Analytics Service",
        description="Life analytics (port 8008)",
        version=settings.SERVICE_VERSION,
        lifespan=lifespan,
    )
    application.middleware("http")(add_correlation_id)

    @application.get("/health")
    async def health_check():
        return {
            "status": "ok",
            "service": settings.SERVICE_NAME,
            "version": settings.SERVICE_VERSION,
        }

    @application.post("/ingest")
    async def ingest(request: Request):
        correlation_id = request.state.correlation_id
        form = await request.form()
        upload = form.get("file")
        data = b""
        filename = str(form.get("filename") or "")
        if upload is not None and hasattr(upload, "read"):
            data = await upload.read()
            filename = filename or getattr(upload, "filename", "") or ""
        user_id = str(form.get("user_id") or "")
        tier = _tier(request, str(form.get("subscription_tier") or "") or None)
        log_with_correlation(correlation_id, "info", f"POST /ingest user_id={user_id} tier={tier}")
        ensure_premium(tier)
        try:
            return await pipeline.ingest_file(
                user_id=user_id,
                filename=filename,
                data=data,
                correlation_id=correlation_id,
            )
        except (UnsupportedFileError, EmptyFileError) as exc:
            log_with_correlation(correlation_id, "warning", f"POST /ingest rejected: {exc}")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="empty or unsupported file",
            ) from exc
        except LLMTimeoutError as exc:
            log_with_correlation(correlation_id, "error", "LLM service timeout")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="LLM service timeout",
            ) from exc
        except LLMUpstreamError as exc:
            log_with_correlation(correlation_id, "error", f"LLM service error: {exc}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="LLM service error",
            ) from exc

    @application.get("/correlations")
    async def correlations(
        request: Request,
        user_id: str,
        subscription_tier: str | None = None,
    ):
        correlation_id = request.state.correlation_id
        tier = _tier(request, subscription_tier)
        log_with_correlation(correlation_id, "info", f"GET /correlations user_id={user_id}")
        ensure_premium(tier)
        return await pipeline.build_view(user_id)

    @application.get("/insights")
    async def insights(
        request: Request,
        user_id: str,
        subscription_tier: str | None = None,
    ):
        correlation_id = request.state.correlation_id
        log_with_correlation(correlation_id, "info", f"GET /insights user_id={user_id}")
        ensure_premium(_tier(request, subscription_tier))
        view = await pipeline.build_view(user_id)
        return {
            "narrative": view["narrative"],
            "inferred_facts": view["inferred_facts"],
            "llm_used": view["llm_used"],
        }

    @application.get("/metrics")
    async def metrics(
        request: Request,
        user_id: str,
        subscription_tier: str | None = None,
    ):
        correlation_id = request.state.correlation_id
        log_with_correlation(correlation_id, "info", f"GET /metrics user_id={user_id}")
        ensure_premium(_tier(request, subscription_tier))
        rows = await db.list_metrics(user_id)
        return {"metrics": rows}

    @application.get("/metrics/{metric_id}")
    async def metric_by_id(
        metric_id: str,
        request: Request,
        user_id: str,
        subscription_tier: str | None = None,
    ):
        correlation_id = request.state.correlation_id
        log_with_correlation(correlation_id, "info", f"GET /metrics/{metric_id}")
        ensure_premium(_tier(request, subscription_tier))
        return owned_or_404(await db.get_metric(metric_id), user_id)

    @application.get("/snapshots/{snapshot_id}")
    async def snapshot_by_id(
        snapshot_id: str,
        request: Request,
        user_id: str,
        subscription_tier: str | None = None,
    ):
        correlation_id = request.state.correlation_id
        log_with_correlation(correlation_id, "info", f"GET /snapshots/{snapshot_id}")
        ensure_premium(_tier(request, subscription_tier))
        return owned_or_404(await db.get_snapshot(snapshot_id), user_id)

    return application


app = create_app()
