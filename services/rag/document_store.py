"""Document Store — MongoDB Atlas integration.

Provides CRUD operations for document metadata with per-user isolation.
All queries are filtered by user_id to ensure data isolation.
"""

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING

from config import settings


class DocumentStore:
    """MongoDB document store with per-user isolation.

    All operations filter by user_id to ensure multi-tenant data isolation.
    """

    def __init__(self) -> None:
        self._client: AsyncIOMotorClient | None = None
        self._db: AsyncIOMotorDatabase | None = None

    async def connect(self) -> None:
        """Establish connection to MongoDB Atlas."""
        self._client = AsyncIOMotorClient(settings.MONGODB_URI)
        self._db = self._client[settings.MONGODB_DB]
        # Create index for efficient user_id queries
        await self._db.documents.create_index([("user_id", ASCENDING)])

    async def close(self) -> None:
        """Close MongoDB connection."""
        if self._client:
            self._client.close()

    @property
    def db(self) -> AsyncIOMotorDatabase:
        """Get database instance."""
        if self._db is None:
            raise RuntimeError("DocumentStore not connected. Call connect() first.")
        return self._db

    async def insert_document(
        self,
        user_id: str,
        doc_type: str,
        original_path: str,
        triples_path: str,
    ) -> str:
        """Insert a new document metadata record.

        Args:
            user_id: Owner's user ID (for isolation)
            doc_type: Document type (image/pdf/html/eml)
            original_path: Path to original file
            triples_path: Path to generated JSONL triples

        Returns:
            Inserted document ID
        """
        document = {
            "user_id": user_id,
            "type": doc_type,
            "original_path": original_path,
            "triples_path": triples_path,
            "created_at": datetime.now(timezone.utc),
        }
        result = await self.db.documents.insert_one(document)
        return str(result.inserted_id)

    async def get_document(self, doc_id: str, user_id: str) -> dict[str, Any] | None:
        """Get a document by ID, filtered by user_id.

        Args:
            doc_id: Document ID
            user_id: Owner's user ID (for isolation)

        Returns:
            Document dict or None if not found or not owned by user
        """
        from bson import ObjectId

        try:
            result = await self.db.documents.find_one(
                {"_id": ObjectId(doc_id), "user_id": user_id}
            )
        except Exception:
            return None
        if result:
            result["_id"] = str(result["_id"])
        return result

    async def list_documents(self, user_id: str) -> list[dict[str, Any]]:
        """List all documents for a user.

        Args:
            user_id: Owner's user ID (for isolation)

        Returns:
            List of document dicts
        """
        cursor = self.db.documents.find({"user_id": user_id}).sort("created_at", ASCENDING)
        documents = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            documents.append(doc)
        return documents

    async def delete_document(self, doc_id: str, user_id: str) -> bool:
        """Delete a document by ID, filtered by user_id.

        Args:
            doc_id: Document ID
            user_id: Owner's user ID (for isolation)

        Returns:
            True if deleted, False if not found or not owned by user
        """
        from bson import ObjectId

        try:
            result = await self.db.documents.delete_one(
                {"_id": ObjectId(doc_id), "user_id": user_id}
            )
            return result.deleted_count > 0
        except Exception:
            return False


# Singleton instance
document_store = DocumentStore()
