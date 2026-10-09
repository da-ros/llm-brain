"""Shield Service — FastAPI application on port 8009.

Clients never call this port. The API Router is the facade. Scan is
synchronous HTTP: OCR, heuristics, one embed, one LLM call. No Kafka.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

import db
import llm_client
from base import ensure_premium, owned_or_404
from config import get_settings
from exceptions import LLMTimeoutError, LLMUpstreamError
from fastapi import FastAPI, HTTPException, Request, status
from guidelines import GUIDELINES_TEXT
from logging_setup import correlation_id_var, log_with_correlation, logger
from pydantic import BaseModel
from scan import (
    SOURCES,
    collect_evidence,
    decode_file,
    list_item,
    persist_alert,
    public_result,
    reset_gallery,
    warm_gallery,
)


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
    try:
        await warm_gallery("startup")
    except Exception:
        logger.exception("Corpus embed failed at startup (scans still call the LLM)")
    yield
    reset_gallery()
    await db.disconnect()


class ScanBody(BaseModel):
    user_id: str = ""
    subscription_tier: str | None = None
    source: str = ""
    text: str = ""
    filename: str = ""
    content_type: str = ""
    content_base64: str = ""


def create_app() -> FastAPI:
    """Build the FastAPI application (used by tests and uvicorn)."""
    settings = get_settings()
    application = FastAPI(
        title="Shield Service",
        description="Privacy and scam shield (port 8009)",
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

    @application.post("/scan")
    async def scan(request: Request):
        correlation_id = request.state.correlation_id
        payload = await _read_scan(request)
        tier = payload["subscription_tier"] or request.headers.get("X-Subscription-Tier") or "free"
        user_id = payload["user_id"]
        source = payload["source"]
        text = payload["text"].strip()
        file_bytes: bytes = payload["file_bytes"]
        log_with_correlation(
            correlation_id,
            "info",
            f"POST /scan user_id={user_id} source={source} tier={tier}",
        )
        ensure_premium(tier)
        if source not in SOURCES or (not text and not file_bytes):
            log_with_correlation(correlation_id, "warning", "POST /scan missing content or source")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="text or file is required, and source must be valid",
            )
        if len(file_bytes) > settings.MAX_UPLOAD_BYTES:
            log_with_correlation(correlation_id, "warning", "POST /scan file too large")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="file exceeds 20 MB",
            )

        existing = await db.find_by_correlation(correlation_id)
        if existing is not None:
            if existing.get("user_id") != user_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
            log_with_correlation(
                correlation_id,
                "info",
                "correlation_id hit — returning stored scan",
            )
            return public_result(existing)

        evidence = await collect_evidence(
            pasted=text,
            source=source,
            file_bytes=file_bytes,
            filename=payload["filename"],
            correlation_id=correlation_id,
        )
        try:
            verdict = await llm_client.judge(
                pasted=text,
                ocr_text=evidence["ocr_text"],
                heuristic_ids=evidence["heuristic_ids"],
                nearest_id=evidence["nearest_id"],
                nearest_score=evidence["nearest_score"],
                embedding_unavailable=evidence["embedding_unavailable"],
                user_id=user_id,
                correlation_id=correlation_id,
                media=file_bytes if source in {"image", "video"} else b"",
                media_type=source if source in {"image", "video"} else "",
            )
        except LLMTimeoutError as exc:
            log_with_correlation(correlation_id, "error", "LLM failure — no persist")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="LLM service timeout",
            ) from exc
        except LLMUpstreamError as exc:
            log_with_correlation(correlation_id, "error", "LLM failure — no persist")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="LLM service error",
            ) from exc

        reasons = list(evidence["reasons"])
        reasons.append({"type": "llm", "id": "llm", "detail": verdict["rationale"]})
        result: dict[str, Any] = {
            "alert": verdict["alert"],
            "likelihood": verdict["likelihood"],
            "severity": verdict["severity"],
            "summary": verdict["summary"],
            "rationale": verdict["rationale"],
            "reasons": reasons,
            "llm_used": True,
        }
        stored = await persist_alert(
            user_id=user_id,
            correlation_id=correlation_id,
            source=source,
            verdict=verdict,
            reasons=reasons,
            result=result,
        )
        result["incident_id"] = str(stored["_id"])
        return result

    @application.get("/incidents")
    async def list_incidents(
        request: Request,
        user_id: str,
        subscription_tier: str | None = None,
    ):
        correlation_id = request.state.correlation_id
        tier = subscription_tier or request.headers.get("X-Subscription-Tier") or "free"
        log_with_correlation(correlation_id, "info", f"GET /incidents user_id={user_id}")
        ensure_premium(tier)
        rows = await db.list_for_user(user_id)
        return {"incidents": [list_item(row) for row in rows]}

    @application.get("/incidents/{incident_id}")
    async def get_incident(
        incident_id: str,
        request: Request,
        user_id: str,
        subscription_tier: str | None = None,
    ):
        correlation_id = request.state.correlation_id
        tier = subscription_tier or request.headers.get("X-Subscription-Tier") or "free"
        log_with_correlation(
            correlation_id,
            "info",
            f"GET /incidents/{incident_id} user_id={user_id}",
        )
        ensure_premium(tier)
        document = owned_or_404(await db.find_by_id(incident_id), user_id)
        return list_item(document)

    @application.delete("/incidents/{incident_id}")
    async def delete_incident(
        incident_id: str,
        request: Request,
        user_id: str,
        subscription_tier: str | None = None,
    ):
        correlation_id = request.state.correlation_id
        tier = subscription_tier or request.headers.get("X-Subscription-Tier") or "free"
        log_with_correlation(
            correlation_id,
            "info",
            f"DELETE /incidents/{incident_id} user_id={user_id}",
        )
        ensure_premium(tier)
        deleted = await db.delete_for_user(incident_id, user_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        return {"deleted": True, "id": incident_id}

    @application.get("/guidelines")
    async def guidelines(
        request: Request,
        user_id: str = "",
        subscription_tier: str | None = None,
    ):
        correlation_id = request.state.correlation_id
        tier = subscription_tier or request.headers.get("X-Subscription-Tier") or "free"
        log_with_correlation(correlation_id, "info", "GET /guidelines")
        ensure_premium(tier)
        return {"text": GUIDELINES_TEXT}

    logger.info("Shield Service ready — port=%s", settings.SHIELD_PORT)
    return application


async def _read_scan(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file")
        file_bytes = b""
        filename = str(form.get("filename") or "")
        if upload is not None and hasattr(upload, "read"):
            file_bytes = await upload.read()
            filename = filename or getattr(upload, "filename", "") or ""
        return {
            "user_id": str(form.get("user_id") or ""),
            "subscription_tier": str(form.get("subscription_tier") or "") or None,
            "source": str(form.get("source") or "").strip().lower(),
            "text": str(form.get("text") or ""),
            "filename": filename,
            "file_bytes": file_bytes,
        }
    body = ScanBody.model_validate(await request.json())
    file_bytes = decode_file(body.content_base64) if body.content_base64 else b""
    return {
        "user_id": body.user_id,
        "subscription_tier": body.subscription_tier,
        "source": body.source.strip().lower(),
        "text": body.text,
        "filename": body.filename,
        "file_bytes": file_bytes,
    }


app = create_app()
