"""ETL Service — FastAPI application.

Standalone memory-distillation microservice on port 8001.
No upload HTTP endpoint (API Router owns POST /api/upload). POST /parse is an
ephemeral text extractor for chat attachments — bytes in, text out, nothing
stored. Health stays 200 regardless of Kafka / distillation activity.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from base import documents_to_content, select, supported_types_message
from config import get_settings
from exceptions import CorruptFileError, LoaderError, UnsupportedFileTypeError
from fastapi import FastAPI, HTTPException, Request, status
from logging_setup import correlation_id_var, log_with_correlation, logger

# Whitelist suffix → MIME for everything /parse accepts. Detection here is
# suffix-only on purpose: the endpoint is ephemeral (chat attachments always
# arrive with the UI's extension list), and no request input may reach a Path.
# Image/video suffixes are listed so a photo or short clip is parsed, not rejected.
_PARSE_SUFFIX_MIME = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".ics": "text/calendar",
    ".html": "text/html",
    ".htm": "text/html",
    ".eml": "message/rfc822",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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


def _show_visual(correlation_id: str, mime: str, exc: Exception) -> dict:
    """A photo or clip the loader cannot read is still shown to the model."""
    log_with_correlation(
        correlation_id,
        "warning",
        f"POST /parse visual loader failed, showing the file to the model: {exc}",
    )
    return {"text": "", "mime": mime, "show_bytes": True}


def _load_attachment(file: bytes, suffix: str, mime: str, correlation_id: str) -> dict:
    """Run the LangChain loader. Empty OCR on a photo or clip asks the caller to show the bytes."""
    visual = mime.startswith(("image/", "video/"))
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"attachment{suffix or '.bin'}"
        path.write_bytes(file)
        try:
            loader_cls = select(str(path), mime_type=mime)
            documents = loader_cls(str(path)).load()
            text = documents_to_content(documents)
        except CorruptFileError as exc:
            if not visual:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
                ) from exc
            # OCR or the clip loader found no words. The caller still has
            # the bytes and shows them to the LLM. This route does not.
            return {"text": "", "mime": mime, "show_bytes": True}
        except UnsupportedFileTypeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        except LoaderError as exc:
            if visual:
                return _show_visual(correlation_id, mime, exc)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        except Exception as exc:  # surface any loader crash as a clean 422
            if visual:
                return _show_visual(correlation_id, mime, exc)
            log_with_correlation(correlation_id, "warning", f"POST /parse failed: {exc}")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not read that file",
            ) from exc
        return {"text": text, "mime": mime, "show_bytes": False}


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
    async def parse_attachment(request: Request, filename: str = ""):
        """Ephemeral parse for chat attachments: bytes in, text out. Nothing stored.

        The body is the raw file, with or without a content type. Loaders run
        in a worker thread so they do not block the event loop.
        """
        file = await request.body()
        correlation_id = request.state.correlation_id
        if not file:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Attachment is empty",
            )
        # Whitelist suffix only: the raw request filename never reaches a Path
        # and MIME comes from constant map values, never from request bytes.
        raw_name = os.path.basename((filename or "").replace("\\", "/")).lower()
        suffix = ""
        for ext in _PARSE_SUFFIX_MIME:
            if raw_name.endswith(ext):
                suffix = ext
                break
        mime = _PARSE_SUFFIX_MIME.get(suffix)
        if mime is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Unsupported file type: {suffix or 'missing extension'}. "
                    f"{supported_types_message()}"
                ),
            )
        log_with_correlation(
            correlation_id, "info", f"POST /parse filename={filename!r} mime={mime}"
        )
        return await asyncio.to_thread(_load_attachment, file, suffix, mime, correlation_id)

    logger.info("ETL Service ready — port=%s llm=%s", settings.API_PORT, settings.LLM_SERVICE_URL)
    return application


app = create_app()
