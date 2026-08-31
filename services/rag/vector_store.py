"""Vector Store — Chroma/Pinecone abstraction with Fernet encryption.

Provides a unified interface for vector storage with per-user isolation.
Embeddings are encrypted with Fernet before storage.
"""

import base64
from typing import Any, Protocol, runtime_checkable

from cryptography.fernet import Fernet

from config import settings


@runtime_checkable
class VectorStore(Protocol):
    """Protocol for vector store implementations."""

    async def add(
        self, vectors: list[list[float]], metadatas: list[dict[str, Any]], ids: list[str]
    ) -> None:
        """Add vectors with metadata."""
        ...

    async def search(
        self, query_vector: list[float], k: int = 3, user_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Search for similar vectors."""
        ...

    async def delete(self, ids: list[str]) -> None:
        """Delete vectors by ID."""
        ...


class ChromaVectorStore:
    """Chroma vector store for local development."""

    def __init__(self, collection_name: str = "llm_brain_embeddings") -> None:
        import chromadb

        self._client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    async def add(
        self, vectors: list[list[float]], metadatas: list[dict[str, Any]], ids: list[str]
    ) -> None:
        """Add vectors with metadata to Chroma."""
        self._collection.add(
            embeddings=vectors,
            metadatas=metadatas,
            ids=ids,
        )

    async def search(
        self, query_vector: list[float], k: int = 3, user_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Search Chroma for similar vectors."""
        where = {"user_id": user_id} if user_id else None
        results = self._collection.query(
            query_embeddings=[query_vector],
            n_results=k,
            where=where,
        )
        # Flatten results
        output = []
        if results and results["ids"]:
            for i, doc_id in enumerate(results["ids"][0]):
                output.append(
                    {
                        "id": doc_id,
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "distance": results["distances"][0][i] if results["distances"] else 0,
                    }
                )
        return output

    async def delete(self, ids: list[str]) -> None:
        """Delete vectors from Chroma."""
        if ids:
            self._collection.delete(ids=ids)


class PineconeVectorStore:
    """Pinecone vector store for production."""

    def __init__(self, index_name: str = "llm-brain-embeddings") -> None:
        from pinecone import Pinecone

        pc = Pinecone()
        self._index = pc.Index(index_name)

    async def add(
        self, vectors: list[list[float]], metadatas: list[dict[str, Any]], ids: list[str]
    ) -> None:
        """Add vectors with metadata to Pinecone."""
        vectors_to_upsert = [
            {"id": ids[i], "values": vectors[i], "metadata": metadatas[i]}
            for i in range(len(ids))
        ]
        self._index.upsert(vectors=vectors_to_upsert)

    async def search(
        self, query_vector: list[float], k: int = 3, user_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Search Pinecone for similar vectors."""
        filter_dict = {"user_id": user_id} if user_id else None
        results = self._index.query(
            vector=query_vector,
            top_k=k,
            include_metadata=True,
            filter=filter_dict,
        )
        output = []
        for match in results.get("matches", []):
            output.append(
                {
                    "id": match["id"],
                    "metadata": match.get("metadata", {}),
                    "score": match.get("score", 0),
                }
            )
        return output

    async def delete(self, ids: list[str]) -> None:
        """Delete vectors from Pinecone."""
        if ids:
            self._index.delete(ids=ids)


class EncryptedVectorStore:
    """Wrapper that adds Fernet encryption to any VectorStore."""

    def __init__(self, store: VectorStore) -> None:
        self._store = store
        self._fernet = Fernet(settings.FERNET_KEY.encode())

    def _encrypt_vector(self, vector: list[float]) -> str:
        """Encrypt a vector to base64 string."""
        import json

        vector_bytes = json.dumps(vector).encode()
        encrypted = self._fernet.encrypt(vector_bytes)
        return base64.b64encode(encrypted).decode()

    def _decrypt_vector(self, encrypted_b64: str) -> list[float]:
        """Decrypt a base64 string back to vector."""
        import json

        encrypted_bytes = base64.b64decode(encrypted_b64)
        decrypted = self._fernet.decrypt(encrypted_bytes)
        return json.loads(decrypted.decode())

    async def add(
        self, vectors: list[list[float]], metadatas: list[dict[str, Any]], ids: list[str]
    ) -> None:
        """Encrypt vectors and add to store."""
        encrypted_vectors = [self._encrypt_vector(v) for v in vectors]
        # Store as encrypted strings in metadata, vectors as dummy zeros
        for i, meta in enumerate(metadatas):
            meta["encrypted_vector"] = encrypted_vectors[i]
        dummy_vectors = [[0.0] * len(vectors[0])] * len(vectors)
        await self._store.add(dummy_vectors, metadatas, ids)

    async def search(
        self, query_vector: list[float], k: int = 3, user_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Search and decrypt results."""
        results = await self._store.search(query_vector, k, user_id)
        for result in results:
            meta = result.get("metadata", {})
            if "encrypted_vector" in meta:
                result["vector"] = self._decrypt_vector(meta["encrypted_vector"])
        return results

    async def delete(self, ids: list[str]) -> None:
        """Delete from underlying store."""
        await self._store.delete(ids)


def create_vector_store(provider: str | None = None) -> VectorStore:
    """Factory: create the appropriate vector store based on config.

    Args:
        provider: "chroma" or "pinecone". If None, uses VectorStoreProvider from config.

    Returns:
        VectorStore instance (encrypted)
    """
    if provider is None:
        provider = settings.VECTOR_STORE_PROVIDER

    if provider == "pinecone":
        store = PineconeVectorStore()
    else:
        store = ChromaVectorStore()

    return EncryptedVectorStore(store)
