"""Upload Router — File upload with Kafka async processing.

Handles file uploads, publishes to Kafka, returns 202 with correlation ID.
"""

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status

from config import settings
from main import verify_token

router = APIRouter(prefix="/api", tags=["upload"])

# Max file size: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024

# Allowed MIME types
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
    user: Annotated[dict, Depends(verify_token)],
):
    """Upload a document for async processing.

    Returns 202 Accepted with correlation ID for polling.
    """
    correlation_id = request.state.correlation_id

    # Check premium tier
    if user.get("subscription_tier") != "premium":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="File upload requires premium subscription",
        )

    # Validate file type
    content_type = file.content_type
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type: {content_type}",
        )

    # Read and validate file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum: {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )

    # Save file to MongoDB (GridFS)
    from motor.motor_asyncio import AsyncIOMotorClient
    from gridfs import GridFS

    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB]
    fs = GridFS(db)

    # Store file in GridFS
    file_id = fs.put(
        content,
        filename=file.filename,
        content_type=content_type,
        user_id=user["user_id"],
    )

    # Create task status record
    task = {
        "_id": correlation_id,
        "user_id": user["user_id"],
        "status": "in_progress",
        "service": "etl-service",
        "endpoint": "http://etl-service:8001/process",
        "file_id": file_id,
        "filename": file.filename,
        "content_type": content_type,
        "retries": 0,
        "max_retries": settings.MAX_RETRIES,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    await db.task_status.insert_one(task)

    # Publish to Kafka
    from kafka import KafkaProducer
    import json

    producer = KafkaProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )

    message = {
        "correlation_id": correlation_id,
        "user_id": user["user_id"],
        "file_id": str(file_id),
        "filename": file.filename,
        "content_type": content_type,
        "service": "etl-service",
        "endpoint": "http://etl-service:8001/process",
    }

    producer.send(settings.KAFKA_TOPIC_FILE_UPLOADED, value=message)
    producer.flush()
    producer.close()

    client.close()

    return {
        "correlation_id": correlation_id,
        "status": "processing",
        "message": "File accepted for processing. Poll GET /tasks/{correlation_id} for status.",
    }
