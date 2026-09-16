"""Vector Store — Chroma (local Docker) + Fernet, Strategy/Factory/Adapter.

Pinecone / managed cloud stores are future work and are not implemented.
"""

from __future__ import annotations

import json
from contextlib import suppress
from typing import Any, Protocol, runtime_checkable

from config import fernet_key_bytes, get_settings
from cryptography.fernet import Fernet
from logging_setup import log_with_correlation, logger


@runtime_checkable
class VectorStore(Protocol):
    """Minimal vector-store contract used by the RAG facade."""

    async def add(
        self,
        vectors: list[list[float]],
        metadatas: list[dict[str, Any]],
        ids: list[str],
        documents: list[str] | None = None,
    ) -> None:
        """Persist vectors with metadata and optional chunk text."""
        ...

    async def search(
        self,
        query_vector: list[float],
        k: int = 3,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return Top-k nearest items, optionally filtered by user_id."""
        ...

    async def delete(self, ids: list[str]) -> None:
        """Delete vectors by ID."""
        ...

    async def delete_where(self, where: dict[str, Any]) -> int:
        """Delete vectors matching metadata filter. Returns count deleted."""
        ...


class ChromaVectorStore:
    """Adapter over the local Chroma HTTP API (Docker, port 8005)."""

    def __init__(
        self,
        collection_name: str | None = None,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        import chromadb

        settings = get_settings()
        self._client = chromadb.HttpClient(
            host=host or settings.CHROMA_HOST,
            port=port or settings.CHROMA_PORT,
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name or settings.CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    async def add(
        self,
        vectors: list[list[float]],
        metadatas: list[dict[str, Any]],
        ids: list[str],
        documents: list[str] | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {
            "embeddings": vectors,
            "metadatas": metadatas,
            "ids": ids,
        }
        if documents is not None:
            kwargs["documents"] = documents
        self._collection.add(**kwargs)

    async def search(
        self,
        query_vector: list[float],
        k: int = 3,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        where = {"user_id": user_id} if user_id else None
        results = self._collection.query(
            query_embeddings=[query_vector],
            n_results=k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        output: list[dict[str, Any]] = []
        if not results or not results.get("ids"):
            return output
        ids = results["ids"][0]
        metadatas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]
        documents = (results.get("documents") or [[]])[0]
        for index, doc_id in enumerate(ids):
            output.append(
                {
                    "id": doc_id,
                    "metadata": metadatas[index] if index < len(metadatas) else {},
                    "distance": distances[index] if index < len(distances) else 0.0,
                    "document": documents[index] if index < len(documents) else "",
                }
            )
        return output

    async def delete(self, ids: list[str]) -> None:
        if ids:
            self._collection.delete(ids=ids)

    async def delete_where(self, where: dict[str, Any]) -> int:
        existing = self._collection.get(where=where, include=[])
        ids = existing.get("ids") or []
        if ids:
            self._collection.delete(ids=ids)
        return len(ids)


class EncryptedVectorStore:
    """Decorator: Fernet-encrypt chunk text + a ciphertext copy of each vector.

    Chroma HNSW needs the raw 2048-dim float vector to run cosine Top-k. Dummy
    zeros (the previous implementation) made search meaningless. This wrapper:

    - stores the real embedding in Chroma's `embeddings` field (ANN index)
    - stores Fernet(vector) in metadata `encrypted_vector` (encrypted at rest)
    - stores Fernet(chunk_text) in Chroma's `documents` field
    - decrypts both on retrieval
    """

    def __init__(self, store: VectorStore) -> None:
        self._store = store
        self._fernet = Fernet(fernet_key_bytes())

    def encrypt_vector(self, vector: list[float]) -> str:
        payload = json.dumps(vector).encode("utf-8")
        return self._fernet.encrypt(payload).decode("utf-8")

    def decrypt_vector(self, token: str) -> list[float]:
        decrypted = self._fernet.decrypt(token.encode("utf-8"))
        return json.loads(decrypted.decode("utf-8"))

    def encrypt_text(self, text: str) -> str:
        return self._fernet.encrypt(text.encode("utf-8")).decode("utf-8")

    def decrypt_text(self, token: str) -> str:
        return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")

    async def add(
        self,
        vectors: list[list[float]],
        metadatas: list[dict[str, Any]],
        ids: list[str],
        documents: list[str] | None = None,
    ) -> None:
        encrypted_docs: list[str] = []
        for index, meta in enumerate(metadatas):
            meta["encrypted_vector"] = self.encrypt_vector(vectors[index])
            meta["encrypted"] = True
            chunk = ""
            if documents is not None and index < len(documents):
                chunk = documents[index]
            elif "chunk_text" in meta:
                chunk = str(meta.pop("chunk_text"))
            encrypted_docs.append(self.encrypt_text(chunk) if chunk else "")
        log_with_correlation(
            "no-id",
            "debug",
            f"Adding {len(vectors)} vectors to Chroma (Fernet ciphertext + ANN index)",
        )
        await self._store.add(vectors, metadatas, ids, encrypted_docs)

    async def search(
        self,
        query_vector: list[float],
        k: int = 3,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        results = await self._store.search(query_vector, k, user_id)
        for result in results:
            meta = result.get("metadata") or {}
            token = meta.get("encrypted_vector")
            if token:
                result["vector"] = self.decrypt_vector(str(token))
            document = result.get("document") or ""
            if document:
                with suppress(Exception):
                    result["document"] = self.decrypt_text(str(document))
        return results

    async def delete(self, ids: list[str]) -> None:
        await self._store.delete(ids)

    async def delete_where(self, where: dict[str, Any]) -> int:
        return await self._store.delete_where(where)


def create_vector_store(provider: str | None = None) -> VectorStore:
    """Factory Method: select the vector-store strategy from config.

    MVP: `chroma` only. Pinecone / managed cloud stores are out of scope.
    """
    settings = get_settings()
    chosen = (provider or settings.VECTOR_STORE_PROVIDER).strip().lower()
    if chosen != "chroma":
        raise ValueError(
            f"Unsupported VECTOR_STORE_PROVIDER={chosen!r}. "
            "MVP supports 'chroma' only (Pinecone is future work)."
        )
    logger.info("Creating Chroma vector store at %s:%s", settings.CHROMA_HOST, settings.CHROMA_PORT)
    return EncryptedVectorStore(ChromaVectorStore())
