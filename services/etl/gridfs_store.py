"""Fetch original binaries from local MongoDB GridFS."""

from __future__ import annotations

from bson import ObjectId
from config import get_settings
from logging_setup import log_with_correlation


def fetch_file(
    file_id: str,
    *,
    correlation_id: str = "no-id",
) -> tuple[bytes, str | None, str | None]:
    """Return (bytes, filename, content_type) for a GridFS file_id."""
    from gridfs import GridFS
    from pymongo import MongoClient

    settings = get_settings()
    log_with_correlation(correlation_id, "info", "Fetching file from MongoDB GridFS (local)")
    client = MongoClient(settings.MONGODB_URI)
    try:
        fs = GridFS(client[settings.MONGODB_DB])
        grid_out = fs.get(ObjectId(file_id))
        payload = grid_out.read()
        filename = getattr(grid_out, "filename", None)
        metadata = getattr(grid_out, "metadata", None) or {}
        content_type = metadata.get("content_type")
        log_with_correlation(correlation_id, "info", "File fetched successfully")
        return payload, filename, content_type
    finally:
        client.close()
