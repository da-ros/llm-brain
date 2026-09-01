"""Tests for RAG service — Document Store, Vector Store, and RAG retrieval."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set env vars BEFORE any imports
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["FERNET_KEY"] = "QmSFavzoGj9MohzGATx3CnkOR2I9JTP4ueRhP4P4DZ0="

# Add services/rag to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "rag"))


# --- Document Store Tests ---


class TestDocumentStore:
    """Tests for MongoDB document store with user_id isolation."""

    @pytest.mark.asyncio
    async def test_insert_document(self):
        """Test inserting a document with user_id."""
        from services.rag.document_store import DocumentStore

        store = DocumentStore()
        mock_db = MagicMock()
        store._db = mock_db

        mock_db.documents.insert_one = AsyncMock(
            return_value=MagicMock(inserted_id="doc123")
        )

        doc_id = await store.insert_document(
            user_id="user1",
            doc_type="pdf",
            original_path="/path/to/file.pdf",
            triples_path="/path/to/triples.jsonl",
        )

        assert doc_id == "doc123"
        mock_db.documents.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_documents_isolation(self):
        """Test that list_documents only returns user's documents."""
        from services.rag.document_store import DocumentStore

        store = DocumentStore()
        mock_db = MagicMock()
        store._db = mock_db

        # Mock cursor that returns only user1's documents
        docs_list = [
            {"_id": "doc1", "user_id": "user1", "type": "pdf"},
            {"_id": "doc2", "user_id": "user1", "type": "html"},
        ]

        class AsyncCursor:
            def __init__(self, docs):
                self._docs = docs
                self._index = 0

            def sort(self, *args):
                return self

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._index >= len(self._docs):
                    raise StopAsyncIteration
                doc = self._docs[self._index]
                self._index += 1
                return doc

        mock_db.documents.find.return_value = AsyncCursor(docs_list)

        docs = await store.list_documents("user1")

        assert len(docs) == 2
        assert all(d["user_id"] == "user1" for d in docs)
        mock_db.documents.find.assert_called_with({"user_id": "user1"})

    @pytest.mark.asyncio
    async def test_get_document_wrong_user(self):
        """Test that get_document returns None for wrong user."""
        from services.rag.document_store import DocumentStore

        store = DocumentStore()
        mock_db = MagicMock()
        store._db = mock_db

        mock_db.documents.find_one = AsyncMock(return_value=None)

        result = await store.get_document("doc123", "wrong_user")

        assert result is None


# --- Vector Store Tests ---


class TestVectorStore:
    """Tests for vector store operations."""

    def test_encrypt_decrypt_vector(self):
        """Test Fernet encryption roundtrip."""
        from services.rag.vector_store import EncryptedVectorStore

        mock_store = MagicMock()
        encrypted_store = EncryptedVectorStore(mock_store)

        original_vector = [0.1, 0.2, 0.3, 0.4, 0.5]
        encrypted = encrypted_store._encrypt_vector(original_vector)
        decrypted = encrypted_store._decrypt_vector(encrypted)

        assert decrypted == pytest.approx(original_vector)

    @pytest.mark.asyncio
    async def test_search_returns_decrypted_vectors(self):
        """Test that search decrypts vectors."""
        from services.rag.vector_store import EncryptedVectorStore

        mock_store = MagicMock()
        encrypted_store = EncryptedVectorStore(mock_store)

        original_vector = [0.1, 0.2, 0.3]
        encrypted = encrypted_store._encrypt_vector(original_vector)

        mock_store.search = AsyncMock(
            return_value=[
                {
                    "id": "doc1",
                    "metadata": {"encrypted_vector": encrypted, "user_id": "user1"},
                    "distance": 0.1,
                }
            ]
        )

        results = await encrypted_store.search([0.1, 0.2, 0.3], k=1, user_id="user1")

        assert len(results) == 1
        assert results[0]["vector"] == pytest.approx(original_vector)


# --- RAG Service Tests ---


class TestRAGService:
    """Tests for RAG service operations."""

    def test_chunk_text(self):
        """Test text chunking."""
        from services.rag.rag_service import RAGService

        service = RAGService()
        text = "A" * 2500  # 2500 chars

        chunks = service.chunk_text(text)

        assert len(chunks) > 1
        assert all(len(chunk) <= 1000 for chunk in chunks)

    def test_embed_text(self):
        """Test embedding generation."""
        from services.rag.rag_service import RAGService

        service = RAGService()
        embedding = service.embed_text("test sentence")

        assert isinstance(embedding, list)
        assert len(embedding) == 384  # sentence-transformers default

    @pytest.mark.asyncio
    async def test_ingest_triples(self):
        """Test triple ingestion from JSONL."""
        from services.rag.rag_service import RAGService

        service = RAGService()
        service._vector_store = MagicMock()
        service._vector_store.add = AsyncMock()

        # Create temp JSONL file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            json.dump(
                {"subject": "Patient", "predicate": "has", "object": "diabetes"},
                f,
            )
            f.write("\n")
            json.dump(
                {"subject": "Patient", "predicate": "takes", "object": "metformin"},
                f,
            )
            f.write("\n")
            triples_path = f.name

        try:
            count = await service.ingest_triples("user1", "doc1", triples_path)

            assert count == 2
            service._vector_store.add.assert_called_once()
        finally:
            Path(triples_path).unlink()

    @pytest.mark.asyncio
    async def test_context_injection_empty(self):
        """Test context injection when no documents exist."""
        from services.rag.rag_service import RAGService

        service = RAGService()
        service._vector_store = MagicMock()
        service._vector_store.search = AsyncMock(return_value=[])

        context = await service.context_injection("test query", "user1")

        assert context == "No relevant context found in your documents."


# --- Integration Tests ---


class TestRAGIntegration:
    """Integration tests for the full RAG pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_mock(self):
        """Test upload -> distill -> embed -> retrieve (mocked)."""
        from services.rag.rag_service import RAGService

        service = RAGService()
        service._vector_store = MagicMock()
        service._vector_store.add = AsyncMock()
        service._vector_store.search = AsyncMock(
            return_value=[
                {
                    "id": "user1_doc1_0_chunk0",
                    "metadata": {
                        "text": "Patient has diabetes",
                        "user_id": "user1",
                        "doc_id": "doc1",
                        "source": "receta.pdf",
                    },
                    "distance": 0.1,
                }
            ]
        )

        # Ingest
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            json.dump(
                {"subject": "Patient", "predicate": "has", "object": "diabetes"},
                f,
            )
            f.write("\n")
            triples_path = f.name

        try:
            count = await service.ingest_triples("user1", "doc1", triples_path)
            assert count == 1

            # Search
            results = await service.semantic_search("diabetes", "user1")
            assert len(results) == 1

            # Context injection
            context = await service.context_injection("diabetes", "user1")
            assert "diabetes" in context.lower() or "patient" in context.lower()
        finally:
            Path(triples_path).unlink()
