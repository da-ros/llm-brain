"""RAG Service — LangChain retrieval facade (chunk, embed, search, inject).

Depends on VectorStore and Embedder abstractions (DIP). Per-user isolation
is enforced on every query via user_id.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import get_settings
from document_store import DocumentStore, document_store
from embeddings import Embedder, create_embedder
from langchain_text_splitters import RecursiveCharacterTextSplitter
from logging_setup import log_with_correlation
from vector_store import VectorStore, create_vector_store

IMAGE_TYPES = {"image", "image/jpeg", "image/png", "image/webp", "image/gif"}
VIDEO_TYPES = {"video", "video/mp4", "video/webm", "video/quicktime"}


def _clip_summary(texts: list[str], limit: int = 180) -> str:
    compact = " ".join(" ".join(texts).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def modality_from_type(doc_type: str | None) -> str:
    """Map a document type / MIME to text | image | video."""
    value = (doc_type or "text").lower()
    if value in IMAGE_TYPES or value.startswith("image/"):
        return "image"
    if value in VIDEO_TYPES or value.startswith("video/"):
        return "video"
    return "text"


class RAGService:
    """Facade: ingest JSONL triples, Top-k search, LLM context injection."""

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        embedder: Embedder | None = None,
        store: DocumentStore | None = None,
    ) -> None:
        settings = get_settings()
        self._vector_store = vector_store
        self._embedder = embedder
        self._document_store = store
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.RAG_CHUNK_SIZE,
            chunk_overlap=settings.RAG_CHUNK_OVERLAP,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    @property
    def vector_store(self) -> VectorStore:
        if self._vector_store is None:
            self._vector_store = create_vector_store()
        return self._vector_store

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = create_embedder()
        return self._embedder

    @property
    def documents(self) -> DocumentStore:
        if self._document_store is None:
            self._document_store = document_store
        return self._document_store

    def embed_text(self, text: str) -> list[float]:
        """Generate a 2048-dim embedding for text (shared multimodal space)."""
        return self.embedder.embed_text(text)

    def embed_query(self, modality: str, *, text: str = "", payload: bytes = b"") -> list[float]:
        """Query vector only. Callers must not write the result to Chroma."""
        if modality == "text":
            return self.embedder.embed_text(text)
        if modality == "image":
            return self.embedder.embed_image(payload)
        if modality == "video":
            return self.embedder.embed_video(payload)
        raise ValueError(f"unsupported modality: {modality}")

    def chunk_text(self, text: str) -> list[str]:
        """Split text with RecursiveCharacterTextSplitter (1000 / 200)."""
        if not text:
            return []
        if len(text) <= get_settings().RAG_CHUNK_SIZE:
            return [text]
        return self._splitter.split_text(text)

    async def ingest_triples(
        self,
        user_id: str,
        doc_id: str,
        triples_path: str,
        *,
        gridfs_id: str = "",
        doc_type: str = "text",
        filename: str = "",
        correlation_id: str = "no-id",
    ) -> int:
        """Read Frame 2 JSONL, chunk, embed (2048-dim), encrypt, store in Chroma."""
        path = Path(triples_path)
        if not path.exists():
            log_with_correlation(
                correlation_id,
                "warning",
                f"JSONL not found: {triples_path}",
            )
            return 0

        texts: list[str] = []
        sources: list[str] = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    triple = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = " ".join(
                    str(triple.get(key, "")).strip()
                    for key in ("subject", "predicate", "object")
                    if triple.get(key)
                )
                if not text:
                    continue
                texts.append(text)
                sources.append(str((triple.get("metadata") or {}).get("source_file", "")))

        if not texts:
            return 0

        modality = modality_from_type(doc_type)
        chunks: list[str] = []
        metadatas: list[dict[str, Any]] = []
        ids: list[str] = []
        for index, text in enumerate(texts):
            for chunk_index, chunk in enumerate(self.chunk_text(text)):
                chunks.append(chunk)
                metadatas.append(
                    {
                        "user_id": user_id,
                        "doc_id": doc_id,
                        "gridfs_id": gridfs_id,
                        "modality": "text",
                        "triple_index": index,
                        "chunk_index": chunk_index,
                        "source": sources[index],
                    }
                )
                ids.append(f"{user_id}_{doc_id}_{index}_chunk{chunk_index}")

        if modality in {"image", "video"} and gridfs_id:
            payload = await self.documents.get_binary(gridfs_id, user_id)
            if payload:
                if modality == "image":
                    vector = self.embedder.embed_image(payload)
                else:
                    vector = self.embedder.embed_video(payload)
                chunks.append(f"{modality} binary gridfs_id={gridfs_id}")
                metadatas.append(
                    {
                        "user_id": user_id,
                        "doc_id": doc_id,
                        "gridfs_id": gridfs_id,
                        "modality": modality,
                        "triple_index": -1,
                        "chunk_index": 0,
                        "source": sources[0] if sources else "",
                    }
                )
                ids.append(f"{user_id}_{doc_id}_{modality}")
                embeddings = [self.embed_text(chunk) for chunk in chunks[:-1]]
                embeddings.append(vector)
            else:
                embeddings = [self.embed_text(chunk) for chunk in chunks]
        else:
            embeddings = [self.embed_text(chunk) for chunk in chunks]

        log_with_correlation(
            correlation_id,
            "debug",
            f"Embedding {len(embeddings)} chunks ({get_settings().EMBEDDING_DIM} dims)",
        )
        await self.vector_store.add(embeddings, metadatas, ids, documents=chunks)

        try:
            await self.documents.insert_document(
                user_id=user_id,
                doc_type=modality,
                gridfs_id=gridfs_id,
                triples_path=triples_path,
                correlation_id=correlation_id,
                filename=filename or (sources[0] if sources else ""),
                content_type=doc_type,
                summary=_clip_summary(texts),
                source_id=doc_id,
            )
        except Exception as exc:
            log_with_correlation(
                correlation_id,
                "warning",
                f"Document index insert skipped: {exc}",
            )

        return len(texts)

    async def semantic_search(
        self,
        query: str,
        user_id: str,
        k: int | None = None,
        *,
        correlation_id: str = "no-id",
    ) -> list[dict[str, Any]]:
        """Embed the query and return Top-k matches for this user only."""
        if k is None:
            k = get_settings().RAG_TOP_K
        log_with_correlation(
            correlation_id,
            "debug",
            f"Searching Chroma with k={k}, user_id={user_id}",
        )
        query_embedding = self.embed_text(query)
        return await self.vector_store.search(query_embedding, k, user_id)

    async def top_k_retrieval(
        self,
        query: str,
        user_id: str,
        k: int | None = None,
        *,
        correlation_id: str = "no-id",
    ) -> list[dict[str, Any]]:
        """LangChain-style Top-k retrieval (same as semantic_search)."""
        return await self.semantic_search(query, user_id, k, correlation_id=correlation_id)

    async def context_injection(
        self,
        query: str,
        user_id: str,
        *,
        correlation_id: str = "no-id",
    ) -> str:
        """Format Top-k chunks as LLM context. Empty corpus → explicit message."""
        results = await self.semantic_search(query, user_id, correlation_id=correlation_id)
        if not results:
            log_with_correlation(correlation_id, "info", "No relevant context found")
            return "No relevant context found in your documents."

        parts: list[str] = []
        for index, result in enumerate(results, 1):
            meta = result.get("metadata") or {}
            text = result.get("document") or meta.get("chunk_text") or meta.get("text") or ""
            source = meta.get("source") or meta.get("gridfs_id") or "unknown"
            parts.append(f"[{index}] {text} (source: {source})")
        return "\n".join(parts)

    async def delete_document_embeddings(self, doc_id: str, user_id: str) -> int:
        """Delete Chroma rows for one document (user-scoped)."""
        return await self.vector_store.delete_where({"user_id": user_id, "doc_id": doc_id})

    async def delete_user_memory(self, user_id: str) -> dict[str, int]:
        """Drop every vector and raw document that belongs to this user."""
        embeddings = await self.vector_store.delete_where({"user_id": user_id})
        documents = await self.documents.delete_all_for_user(user_id)
        return {"documents": documents, "embeddings": embeddings}


rag_service = RAGService()
