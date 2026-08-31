"""RAG Service — LangChain retrieval and context injection.

Orchestrates semantic search, document chunking, and context injection
for LLM queries. Per-user isolation via user_id filtering.
"""

import json
from pathlib import Path
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

from config import settings
from services.rag.document_store import document_store
from services.rag.vector_store import VectorStore, create_vector_store


class RAGService:
    """RAG service for semantic retrieval and context injection.

    Combines vector search with LLM context augmentation.
    All operations are filtered by user_id for multi-tenant isolation.
    """

    def __init__(self) -> None:
        self._vector_store: VectorStore | None = None
        self._embedder: SentenceTransformer | None = None
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.RAG_CHUNK_SIZE,
            chunk_overlap=settings.RAG_CHUNK_OVERLAP,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    @property
    def vector_store(self) -> VectorStore:
        """Get or create vector store instance."""
        if self._vector_store is None:
            self._vector_store = create_vector_store()
        return self._vector_store

    @property
    def embedder(self) -> SentenceTransformer:
        """Get or create embedding model instance."""
        if self._embedder is None:
            self._embedder = SentenceTransformer(settings.EMBEDDING_MODEL)
        return self._embedder

    def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a text string.

        Args:
            text: Text to embed

        Returns:
            384-dimensional vector
        """
        return self.embedder.encode(text).tolist()

    def chunk_text(self, text: str) -> list[str]:
        """Split text into chunks for embedding.

        Args:
            text: Raw text to chunk

        Returns:
            List of text chunks
        """
        return self._splitter.split_text(text)

    async def ingest_triples(
        self, user_id: str, doc_id: str, triples_path: str
    ) -> int:
        """Ingest JSONL triples into the vector store.

        Args:
            user_id: Owner's user ID
            doc_id: Document ID
            triples_path: Path to JSONL file with triples

        Returns:
            Number of triples ingested
        """
        path = Path(triples_path)
        if not path.exists():
            return 0

        texts = []
        metadatas = []
        ids = []

        with open(path) as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    triple = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Build text from triple
                text = f"{triple.get('subject', '')} {triple.get('predicate', '')} {triple.get('object', '')}"
                texts.append(text)
                metadatas.append(
                    {
                        "user_id": user_id,
                        "doc_id": doc_id,
                        "triple_index": i,
                        "source": triple.get("metadata", {}).get("source_file", ""),
                    }
                )
                ids.append(f"{user_id}_{doc_id}_{i}")

        if not texts:
            return 0

        # Chunk texts
        all_chunks = []
        all_metadatas = []
        all_ids = []

        for i, text in enumerate(texts):
            chunks = self.chunk_text(text)
            for j, chunk in enumerate(chunks):
                all_chunks.append(chunk)
                all_metadatas.append(
                    {**metadatas[i], "chunk_index": j}
                )
                all_ids.append(f"{ids[i]}_chunk{j}")

        # Generate embeddings
        embeddings = [self.embed_text(chunk) for chunk in all_chunks]

        # Store in vector store
        await self.vector_store.add(embeddings, all_metadatas, all_ids)

        return len(texts)

    async def semantic_search(
        self, query: str, user_id: str, k: int | None = None
    ) -> list[dict[str, Any]]:
        """Search for relevant documents using semantic similarity.

        Args:
            query: Natural language query
            user_id: Owner's user ID (for isolation)
            k: Number of results (default from config)

        Returns:
            List of relevant document chunks with metadata
        """
        if k is None:
            k = settings.RAG_TOP_K

        query_embedding = self.embed_text(query)
        results = await self.vector_store.search(query_embedding, k, user_id)
        return results

    async def context_injection(self, query: str, user_id: str) -> str:
        """Retrieve context and format it for LLM injection.

        Args:
            query: User's question
            user_id: Owner's user ID

        Returns:
            Formatted context string ready for LLM prompt
        """
        results = await self.semantic_search(query, user_id)

        if not results:
            return "No relevant context found in your documents."

        context_parts = []
        for i, result in enumerate(results, 1):
            meta = result.get("metadata", {})
            text = meta.get("text", str(meta))
            source = meta.get("source", "unknown")
            context_parts.append(f"[{i}] {text} (source: {source})")

        return "\n".join(context_parts)

    async def delete_document_embeddings(self, doc_id: str, user_id: str) -> None:
        """Delete all embeddings for a document.

        Args:
            doc_id: Document ID
            user_id: Owner's user ID
        """
        # Search for all chunks belonging to this document
        results = await self.semantic_search(
            f"document {doc_id}", user_id, k=1000
        )
        ids_to_delete = [
            r["id"]
            for r in results
            if r.get("metadata", {}).get("doc_id") == doc_id
        ]
        if ids_to_delete:
            await self.vector_store.delete(ids_to_delete)


# Singleton instance
rag_service = RAGService()
