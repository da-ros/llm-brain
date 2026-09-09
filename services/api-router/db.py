"""MongoDB access for task_status polling and GridFS uploads.

Business documents live in other services. The router only stores:
- uploaded files in GridFS (so ETL can fetch them)
- task_status documents with a TTL index on expires_at
"""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from typing import Any

from config import get_settings
from logging_setup import logger

_client = None
_database = None


async def connect() -> None:
    """Open the Motor client used by request handlers."""
    global _client, _database
    from motor.motor_asyncio import AsyncIOMotorClient

    settings = get_settings()
    _client = AsyncIOMotorClient(settings.MONGODB_URI)
    _database = _client[settings.MONGODB_DB]
    logger.info("Connected to MongoDB")


async def disconnect() -> None:
    """Close the Motor client."""
    global _client, _database
    if _client is not None:
        _client.close()
    _client = None
    _database = None


def _db():
    if _database is None:
        raise RuntimeError("MongoDB is not connected")
    return _database


async def ensure_indexes() -> None:
    """TTL index: MongoDB deletes task_status rows after expires_at."""
    await _db().task_status.create_index("expires_at", expireAfterSeconds=0)
    logger.info("Ensured task_status TTL index on expires_at")


def task_document(
    *,
    correlation_id: str,
    user_id: str,
    file_id: str,
    filename: str,
    content_type: str,
) -> dict[str, Any]:
    """Build a task_status document as specified in the design."""
    settings = get_settings()
    now = datetime.now(UTC)
    return {
        "_id": correlation_id,
        "user_id": user_id,
        "status": "in_progress",
        "service": "etl-service",
        "endpoint": f"{settings.ETL_SERVICE_URL}/process",
        "file_id": file_id,
        "filename": filename,
        "content_type": content_type,
        "retries": 0,
        "max_retries": settings.MAX_RETRIES,
        "created_at": now,
        "updated_at": now,
        "expires_at": now + timedelta(days=settings.TASK_STATUS_TTL_DAYS),
        "http_code": None,
        "error_message": None,
        "result": None,
    }


async def save_upload(filename: str, content: bytes, content_type: str, user_id: str) -> str:
    """Store the file in GridFS and return the file id as a string."""
    from motor.motor_asyncio import AsyncIOMotorGridFSBucket

    bucket = AsyncIOMotorGridFSBucket(_db())
    file_id = await bucket.upload_from_stream(
        filename or "upload.bin",
        io.BytesIO(content),
        metadata={"content_type": content_type, "user_id": user_id},
    )
    return str(file_id)


async def insert_task(document: dict[str, Any]) -> None:
    await _db().task_status.insert_one(document)


async def find_task(correlation_id: str) -> dict[str, Any] | None:
    return await _db().task_status.find_one({"_id": correlation_id})


async def update_task(correlation_id: str, updates: dict[str, Any]) -> None:
    payload = {**updates, "updated_at": datetime.now(UTC)}
    await _db().task_status.update_one({"_id": correlation_id}, {"$set": payload})
