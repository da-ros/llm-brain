"""Upload router — Premium-only, async via Kafka.

POST /api/upload → python-magic MIME + 10MB + GridFS + file.uploaded → 202 Accepted
"""

from typing import Annotated

import db
from auth import require_premium
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from kafka_io import file_uploaded_message, publish_file_uploaded
from logging_setup import log_with_correlation
from mimeutil import detect_mime, is_allowed_upload_mime, supported_types_message
from rate_limit import rate_limit_upload

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_file(
    request: Request,
    file: UploadFile,
    user: Annotated[dict, Depends(require_premium)],
    _: Annotated[dict, Depends(rate_limit_upload)],
):
    """Accept a document for async ETL processing."""
    from config import get_settings

    correlation_id = request.state.correlation_id
    settings = get_settings()

    log_with_correlation(correlation_id, "info", "POST /api/upload")
    log_with_correlation(
        correlation_id,
        "info",
        f"JWT validated: user_id={user['user_id']}, tier={user['subscription_tier']}",
    )

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"File too large. Maximum: {settings.MAX_UPLOAD_BYTES // (1024 * 1024)}MB",
                )
        except ValueError:
            pass

    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File too large. Maximum: {settings.MAX_UPLOAD_BYTES // (1024 * 1024)}MB",
        )

    mime_type = detect_mime(content, filename=file.filename)
    if not is_allowed_upload_mime(mime_type):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported file type: {mime_type}. {supported_types_message()}",
        )

    file_id = await db.save_upload(
        filename=file.filename or "upload.bin",
        content=content,
        content_type=mime_type,
        user_id=user["user_id"],
    )
    log_with_correlation(
        correlation_id,
        "info",
        f"File saved to GridFS: {file.filename} (user_id={user['user_id']})",
    )

    task = db.task_document(
        correlation_id=correlation_id,
        user_id=user["user_id"],
        file_id=file_id,
        filename=file.filename or "upload.bin",
        content_type=mime_type,
    )
    await db.insert_task(task)
    log_with_correlation(correlation_id, "info", "Task status created: in_progress")

    publish_file_uploaded(file_uploaded_message(task))
    log_with_correlation(correlation_id, "info", "Response: 202 Accepted")

    return {
        "correlation_id": correlation_id,
        "status": "processing",
        "message": "File accepted for processing. Poll GET /tasks/{correlation_id} for status.",
    }
