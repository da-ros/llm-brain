"""Upload router — Premium-only, async via Kafka.

POST /api/upload → GridFS + task_status + file.uploaded → 202 Accepted
"""

from typing import Annotated

import db
from auth import require_premium
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from kafka_io import file_uploaded_message, publish_file_uploaded
from logging_setup import log_with_correlation
from rate_limit import rate_limit_upload

router = APIRouter(prefix="/api", tags=["upload"])

ALLOWED_TYPES = {
    "application/pdf",
    "text/html",
    "message/rfc822",
    "image/png",
    "image/jpeg",
    "image/tiff",
}


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

    content_type = file.content_type or ""
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type: {content_type}",
        )

    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum: {settings.MAX_UPLOAD_BYTES // (1024 * 1024)}MB",
        )

    file_id = await db.save_upload(
        filename=file.filename or "upload.bin",
        content=content,
        content_type=content_type,
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
        content_type=content_type,
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
