"""Document Store — local MongoDB + GridFS with per-user isolation.

Schema: {_id, user_id, type, gridfs_id, triples_path, created_at}
Binaries live in GridFS; this collection is the Documents index.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from config import get_settings
from logging_setup import log_with_correlation
from pymongo import ASCENDING
from pymongo.errors import PyMongoError


class DocumentStoreError(RuntimeError):
    """Raised when MongoDB / GridFS access fails."""


class DocumentStore:
    """Repository over local MongoDB documents + GridFS binaries."""

    def __init__(self) -> None:
        self._client: Any = None
        self._db: Any = None
        self._fs: Any = None

    async def connect(self) -> None:
        """Establish a pooled connection to local MongoDB."""
        from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket

        settings = get_settings()
        self._client = AsyncIOMotorClient(
            settings.MONGODB_URI,
            maxPoolSize=settings.MONGODB_MAX_POOL_SIZE,
            minPoolSize=settings.MONGODB_MIN_POOL_SIZE,
            serverSelectionTimeoutMS=5000,
        )
        self._db = self._client[settings.MONGODB_DB]
        self._fs = AsyncIOMotorGridFSBucket(self._db)
        await self._db.documents.create_index([("user_id", ASCENDING)])
        await self._db.documents.create_index([("gridfs_id", ASCENDING)])

    async def close(self) -> None:
        """Close the pooled MongoDB client."""
        if self._client is not None:
            self._client.close()
            self._client = None
            self._db = None
            self._fs = None

    @property
    def db(self) -> Any:
        if self._db is None:
            raise RuntimeError("DocumentStore not connected. Call connect() first.")
        return self._db

    @property
    def fs(self) -> Any:
        if self._fs is None:
            raise RuntimeError("DocumentStore not connected. Call connect() first.")
        return self._fs

    async def store_binary(
        self,
        content: bytes,
        *,
        filename: str,
        user_id: str,
        content_type: str,
        correlation_id: str = "no-id",
    ) -> str:
        """Store an original binary in GridFS and return gridfs_id."""
        try:
            file_id = await self.fs.upload_from_stream(
                filename,
                content,
                metadata={"user_id": user_id, "content_type": content_type},
            )
        except PyMongoError as exc:
            log_with_correlation(correlation_id, "error", f"GridFS upload failed: {exc}")
            raise DocumentStoreError(f"GridFS upload failed: {exc}") from exc
        return str(file_id)

    async def get_binary(self, gridfs_id: str, user_id: str) -> bytes | None:
        """Fetch a GridFS binary only if it belongs to user_id."""
        try:
            oid = ObjectId(gridfs_id)
        except (InvalidId, TypeError):
            return None
        try:
            grid_out = await self.fs.open_download_stream(oid)
        except Exception:
            return None
        metadata = getattr(grid_out, "metadata", None) or {}
        if metadata.get("user_id") and metadata.get("user_id") != user_id:
            return None
        chunks: list[bytes] = []
        async for chunk in grid_out:
            chunks.append(chunk)
        return b"".join(chunks)

    async def insert_document(
        self,
        user_id: str,
        doc_type: str,
        gridfs_id: str,
        triples_path: str,
        *,
        correlation_id: str = "no-id",
        content: bytes | None = None,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> str:
        """Insert a Documents index row. Optionally upload `content` to GridFS first."""
        log_with_correlation(
            correlation_id,
            "debug",
            f"Inserting document: user={user_id}, type={doc_type}",
        )
        resolved_gridfs_id = gridfs_id
        if content is not None:
            resolved_gridfs_id = await self.store_binary(
                content,
                filename=filename or "upload.bin",
                user_id=user_id,
                content_type=content_type or doc_type,
                correlation_id=correlation_id,
            )
        document = {
            "user_id": user_id,
            "type": doc_type,
            "gridfs_id": resolved_gridfs_id,
            "triples_path": triples_path,
            "created_at": datetime.now(UTC),
        }
        try:
            result = await self.db.documents.insert_one(document)
        except PyMongoError as exc:
            log_with_correlation(correlation_id, "error", f"Document insert failed: {exc}")
            raise DocumentStoreError(f"Document insert failed: {exc}") from exc
        doc_id = str(result.inserted_id)
        log_with_correlation(correlation_id, "debug", f"Document inserted: doc_id={doc_id}")
        return doc_id

    async def get_document(self, doc_id: str, user_id: str) -> dict[str, Any] | None:
        """Return a document only if it belongs to user_id (else None → HTTP 404)."""
        try:
            oid = ObjectId(doc_id)
        except (InvalidId, TypeError):
            return None
        try:
            result = await self.db.documents.find_one({"_id": oid, "user_id": user_id})
        except PyMongoError:
            return None
        if result is None:
            return None
        result["_id"] = str(result["_id"])
        return result

    async def list_documents(self, user_id: str) -> list[dict[str, Any]]:
        """List documents for one user. Never returns another tenant's rows."""
        try:
            cursor = self.db.documents.find({"user_id": user_id}).sort("created_at", ASCENDING)
            documents: list[dict[str, Any]] = []
            async for doc in cursor:
                doc["_id"] = str(doc["_id"])
                documents.append(doc)
            return documents
        except PyMongoError as exc:
            raise DocumentStoreError(f"Document list failed: {exc}") from exc

    async def delete_document(self, doc_id: str, user_id: str) -> bool:
        """Delete the Documents row and its GridFS binary if owned by user_id."""
        existing = await self.get_document(doc_id, user_id)
        if existing is None:
            return False
        gridfs_id = existing.get("gridfs_id")
        try:
            await self.db.documents.delete_one({"_id": ObjectId(doc_id), "user_id": user_id})
        except (InvalidId, PyMongoError):
            return False
        if gridfs_id:
            with suppress(Exception):
                await self.fs.delete(ObjectId(gridfs_id))
        return True


document_store = DocumentStore()
