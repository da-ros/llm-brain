"""ETL Service — FastAPI application.

Standalone memory-distillation microservice on port 8001.
No upload HTTP endpoint (API Router owns POST /api/upload). POST /parse is an
ephemeral text extractor for chat attachments — bytes in, text out, nothing
stored. Health stays 200 regardless of Kafka / distillation activity.
"""

from __future__ import annotations

import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from base import detect_mime, documents_to_content, select
from config import get_settings
from exceptions import CorruptFileError, LoaderError, UnsupportedFileTypeError
from fastapi import Body, FastAPI, HTTPException, Request, status
from logging_setup import correlation_id_var, log_with_correlation, logger

# Suffixes python-magic cannot pin down reliably; mapped before MIME detection.
# Image/video suffixes are listed so the out-of-scope answer does not depend
# on libmagic being present in the environment.
_PARSE_SUFFIX_MIME = {
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".ics": "text/calendar",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".bmp": "image/bmp",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".mpeg": "video/mpeg",
    ".mpg": "video/mpeg",
}


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup/shutdown events."""
    settings = get_settings()
    if settings.KAFKA_ENABLED:
        from kafka_io import start_consumer_thread

        start_consumer_thread()
    else:
        logger.info("Kafka consumer disabled (KAFKA_ENABLED=false)")
    yield


def create_app() -> FastAPI:
    """Build the FastAPI application (used by tests and uvicorn)."""
    settings = get_settings()
    application = FastAPI(
        title="ETL Service",
        description="One-Tap Memory Distillation — LangChain loaders + LLM triples",
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

    @application.post("/parse")
    def parse_attachment(request: Request, filename: str = "", file: bytes = Body(...)):
        """Ephemeral parse for chat attachments: bytes in, text out. Nothing stored.

        Declared as `def` on purpose — FastAPI runs sync endpoints in a
        threadpool, so the LangChain loaders never block the event loop.
        """
        correlation_id = request.state.correlation_id
        if not file:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Attachment is empty",
            )
        # The temp filename is built only from whitelisted constant suffixes:
        # the raw request filename never reaches the Path (Snyk SAST taint).
        raw_name = os.path.basename((filename or "").replace("\\", "/")).lower()
        suffix = ""
        for ext in _PARSE_SUFFIX_MIME:
            if raw_name.endswith(ext):
                suffix = ext
                break
        try:
            mime = _PARSE_SUFFIX_MIME.get(suffix) or detect_mime(
                file_path=filename or None, content=file
            )
        except UnsupportedFileTypeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        log_with_correlation(
            correlation_id, "info", f"POST /parse filename={filename!r} mime={mime}"
        )
        if mime.startswith(("image/", "video/")):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{mime} attachments are out of scope in this iteration.",
            )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"attachment{suffix or '.bin'}"
            path.write_bytes(file)
            try:
                loader_cls = select(str(path), mime_type=mime)
                documents = loader_cls(str(path)).load()
                return {"text": documents_to_content(documents), "mime": mime}
            except (UnsupportedFileTypeError, CorruptFileError, LoaderError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
                ) from exc
            except Exception as exc:  # surface any loader crash as a clean 422
                log_with_correlation(correlation_id, "warning", f"POST /parse failed: {exc}")
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Could not read that file",
                ) from exc

    logger.info("ETL Service ready — port=%s llm=%s", settings.API_PORT, settings.LLM_SERVICE_URL)
    return application


app = create_app()
