"""Tests for Hybrid Store + RAG — Mongo/GridFS, Chroma, Fernet, retrieval."""

from __future__ import annotations

import json
import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import PyMongoError


class MemoryVectorStore:
    """In-memory VectorStore stand-in so unit tests never need Chroma."""

    def __init__(self) -> None:
        self.items: list[dict] = []

    async def add(self, vectors, metadatas, ids, documents=None) -> None:
        for index, item_id in enumerate(ids):
            self.items.append(
                {
                    "id": item_id,
                    "vector": list(vectors[index]),
                    "metadata": dict(metadatas[index]),
                    "document": documents[index] if documents else "",
                }
            )

    async def search(self, query_vector, k=3, user_id=None):
        scored = []
        for item in self.items:
            if user_id and item["metadata"].get("user_id") != user_id:
                continue
            distance = 1.0 - _cosine(query_vector, item["vector"])
            scored.append((distance, item))
        scored.sort(key=lambda pair: pair[0])
        output = []
        for distance, item in scored[:k]:
            output.append(
                {
                    "id": item["id"],
                    "metadata": item["metadata"],
                    "distance": distance,
                    "document": item["document"],
                }
            )
        return output

    async def delete(self, ids) -> None:
        wanted = set(ids)
        self.items = [item for item in self.items if item["id"] not in wanted]

    async def delete_where(self, where) -> int:
        remaining = []
        deleted = 0
        for item in self.items:
            if all(item["metadata"].get(key) == value for key, value in where.items()):
                deleted += 1
            else:
                remaining.append(item)
        self.items = remaining
        return deleted


def _cosine(left, right) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    norm_l = math.sqrt(sum(a * a for a in left)) or 1.0
    norm_r = math.sqrt(sum(b * b for b in right)) or 1.0
    return dot / (norm_l * norm_r)


class AsyncCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *_args):
        return self

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._index >= len(self._docs):
            raise StopAsyncIteration
        doc = self._docs[self._index]
        self._index += 1
        return doc


def _service(store=None):
    from embeddings import MockEmbedder
    from rag_service import RAGService
    from vector_store import EncryptedVectorStore

    memory = store or MemoryVectorStore()
    docs = MagicMock()
    docs.insert_document = AsyncMock(return_value="doc-mongo-1")
    docs.get_binary = AsyncMock(return_value=None)
    return RAGService(
        vector_store=EncryptedVectorStore(memory),
        embedder=MockEmbedder(dim=2048),
        store=docs,
    ), memory


# --- Document Store ---


class TestDocumentStore:
    @pytest.mark.asyncio
    async def test_insert_document_uses_gridfs_id_schema(self):
        from document_store import DocumentStore

        store = DocumentStore()
        mock_db = MagicMock()
        store._db = mock_db
        mock_db.documents.insert_one = AsyncMock(return_value=MagicMock(inserted_id="doc123"))

        doc_id = await store.insert_document(
            user_id="user1",
            doc_type="pdf",
            gridfs_id="gridfs-1",
            triples_path="/data/triples/user1/doc1.jsonl",
        )

        assert doc_id == "doc123"
        payload = mock_db.documents.insert_one.call_args[0][0]
        assert payload["user_id"] == "user1"
        assert payload["type"] == "pdf"
        assert payload["gridfs_id"] == "gridfs-1"
        assert payload["triples_path"].endswith("doc1.jsonl")
        assert "original_path" not in payload

    @pytest.mark.asyncio
    async def test_list_documents_isolation(self):
        from document_store import DocumentStore

        store = DocumentStore()
        mock_db = MagicMock()
        store._db = mock_db
        docs_list = [
            {"_id": "doc1", "user_id": "user1", "type": "pdf", "gridfs_id": "g1"},
            {"_id": "doc2", "user_id": "user1", "type": "html", "gridfs_id": "g2"},
        ]
        mock_db.documents.find.return_value = AsyncCursor(docs_list)

        docs = await store.list_documents("user1")

        assert len(docs) == 2
        assert all(doc["user_id"] == "user1" for doc in docs)
        mock_db.documents.find.assert_called_with({"user_id": "user1"})

    @pytest.mark.asyncio
    async def test_get_document_wrong_user_returns_none(self):
        from document_store import DocumentStore

        store = DocumentStore()
        mock_db = MagicMock()
        store._db = mock_db
        mock_db.documents.find_one = AsyncMock(return_value=None)

        result = await store.get_document("507f1f77bcf86cd799439011", "wrong_user")

        assert result is None


# --- Vector store / Fernet ---


class TestVectorStore:
    def test_factory_rejects_pinecone(self):
        from vector_store import create_vector_store

        with pytest.raises(ValueError, match="chroma"):
            create_vector_store("pinecone")

    def test_encrypt_decrypt_vector_roundtrip(self):
        from vector_store import EncryptedVectorStore

        wrapper = EncryptedVectorStore(MemoryVectorStore())
        original = [0.1, 0.2, 0.3, 0.4]
        token = wrapper.encrypt_vector(original)
        assert token != json.dumps(original)
        assert wrapper.decrypt_vector(token) == pytest.approx(original)

    @pytest.mark.asyncio
    async def test_embeddings_encrypted_at_rest_decrypted_on_retrieval(self):
        from vector_store import EncryptedVectorStore

        memory = MemoryVectorStore()
        wrapper = EncryptedVectorStore(memory)
        vector = [0.12, -0.45, 0.78]
        await wrapper.add(
            [vector],
            [{"user_id": "user1", "gridfs_id": "g1", "modality": "text"}],
            ["id-1"],
            documents=["Paciente tiene diabetes"],
        )

        stored = memory.items[0]
        assert stored["vector"] == pytest.approx(vector)
        assert stored["metadata"]["encrypted"] is True
        assert stored["metadata"]["encrypted_vector"] != json.dumps(vector)
        assert stored["document"] != "Paciente tiene diabetes"
        with pytest.raises(json.JSONDecodeError):
            json.loads(stored["document"])

        results = await wrapper.search(vector, k=1, user_id="user1")
        assert results[0]["document"] == "Paciente tiene diabetes"
        assert results[0]["vector"] == pytest.approx(vector)

    @pytest.mark.asyncio
    async def test_chroma_adapter_stores_document_and_gridfs_metadata(self):
        from vector_store import ChromaVectorStore

        fake_collection = MagicMock()
        fake_collection.query.return_value = {
            "ids": [["id-1"]],
            "metadatas": [[{"user_id": "user1", "gridfs_id": "g1"}]],
            "distances": [[0.1]],
            "documents": [["chunk"]],
        }
        store = ChromaVectorStore.__new__(ChromaVectorStore)
        store._collection = fake_collection
        await store.add(
            [[0.1] * 8],
            [{"user_id": "user1", "gridfs_id": "g1"}],
            ["id-1"],
            documents=["chunk text"],
        )
        kwargs = fake_collection.add.call_args.kwargs
        assert kwargs["documents"] == ["chunk text"]
        assert kwargs["metadatas"][0]["gridfs_id"] == "g1"


# --- Embeddings ---


class TestEmbeddings:
    def test_mock_embedder_is_2048_dim(self):
        from embeddings import MockEmbedder

        embedder = MockEmbedder(dim=2048)
        vector = embedder.embed_text("Paciente tiene diabetes")
        assert len(vector) == 2048
        assert math.isclose(sum(v * v for v in vector), 1.0, rel_tol=1e-5)

    def test_create_embedder_uses_mock_when_flag_set(self):
        from embeddings import MockEmbedder, create_embedder

        embedder = create_embedder()
        assert isinstance(embedder, MockEmbedder)


# --- RAG service ---


class TestRAGService:
    def test_chunk_text_splits_long_documents(self):
        service, _memory = _service()
        chunks = service.chunk_text("A" * 2500)
        assert len(chunks) > 1
        assert all(len(chunk) <= 1000 for chunk in chunks)

    def test_embed_text_is_2048_dim(self):
        service, _memory = _service()
        embedding = service.embed_text("test sentence")
        assert isinstance(embedding, list)
        assert len(embedding) == 2048

    @pytest.mark.asyncio
    async def test_ingest_triples_from_jsonl(self, tmp_path):
        service, memory = _service()
        path = tmp_path / "doc1.jsonl"
        path.write_text(
            json.dumps({"subject": "Patient", "predicate": "has", "object": "diabetes"})
            + "\n"
            + json.dumps({"subject": "Patient", "predicate": "takes", "object": "metformin"})
            + "\n",
            encoding="utf-8",
        )
        count = await service.ingest_triples(
            "user1",
            "doc1",
            str(path),
            gridfs_id="grid-1",
            doc_type="pdf",
        )
        assert count == 2
        assert memory.items
        assert all(item["metadata"]["gridfs_id"] == "grid-1" for item in memory.items)
        assert all(item["metadata"]["user_id"] == "user1" for item in memory.items)
        service.documents.insert_document.assert_awaited()

    @pytest.mark.asyncio
    async def test_context_injection_empty(self):
        service, _memory = _service()
        context = await service.context_injection("test query", "user1")
        assert context == "No relevant context found in your documents."

    @pytest.mark.asyncio
    async def test_retrieval_quality_known_documents(self, tmp_path):
        service, _memory = _service()
        path = tmp_path / "known.jsonl"
        path.write_text(
            json.dumps({"subject": "Patient", "predicate": "has", "object": "diabetes"})
            + "\n"
            + json.dumps({"subject": "Invoice", "predicate": "total", "object": "42 euros"})
            + "\n",
            encoding="utf-8",
        )
        await service.ingest_triples("user1", "doc1", str(path), gridfs_id="g1")

        results = await service.semantic_search("diabetes treatment", "user1", k=2)
        assert results
        top_text = results[0]["document"].lower()
        assert "diabetes" in top_text

        other = await service.semantic_search("diabetes", "user2", k=3)
        assert other == []

    @pytest.mark.asyncio
    async def test_top_k_retrieval_alias(self, tmp_path):
        service, _memory = _service()
        path = tmp_path / "a.jsonl"
        path.write_text(
            json.dumps({"subject": "Patient", "predicate": "has", "object": "diabetes"}) + "\n",
            encoding="utf-8",
        )
        await service.ingest_triples("user1", "doc1", str(path), gridfs_id="g1")
        results = await service.top_k_retrieval("diabetes", "user1", k=1)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_undecodable_video_keeps_the_description_triples(self, tmp_path):
        service, memory = _service()
        service.documents.get_binary = AsyncMock(return_value=b"not-a-video")
        path = tmp_path / "clip.jsonl"
        path.write_text(
            json.dumps({"subject": "Clip", "predicate": "shows", "object": "a receipt"}) + "\n",
            encoding="utf-8",
        )
        with patch("embeddings.sample_video_frames", return_value=[]):
            count = await service.ingest_triples(
                "user1",
                "doc1",
                str(path),
                gridfs_id="g1",
                doc_type="video/mp4",
            )
        assert count == 1
        assert [item["metadata"].get("modality") for item in memory.items] == ["text"]

    @pytest.mark.asyncio
    async def test_video_ingest_stores_the_averaged_frame_vector(self, tmp_path):
        from embeddings import _average_vectors

        service, memory = _service()
        service.documents.get_binary = AsyncMock(return_value=b"mp4")
        path = tmp_path / "clip.jsonl"
        path.write_text(
            json.dumps({"subject": "Clip", "predicate": "shows", "object": "a receipt"}) + "\n",
            encoding="utf-8",
        )
        frames = [b"start", b"middle", b"end"]
        with patch("embeddings.sample_video_frames", return_value=frames):
            await service.ingest_triples(
                "user1",
                "doc1",
                str(path),
                gridfs_id="g1",
                doc_type="video/mp4",
            )
        video_items = [item for item in memory.items if item["metadata"].get("modality") == "video"]
        assert len(video_items) == 1
        expected = _average_vectors([service.embedder.embed_image(frame) for frame in frames])
        assert video_items[0]["vector"] == expected
        results = await service.semantic_search("receipt", "user1", k=5)
        shown = [
            item["document"] for item in results if item["metadata"].get("modality") == "video"
        ]
        assert shown == ["Clip shows a receipt"]


class TestRAGIntegration:
    @pytest.mark.asyncio
    async def test_upload_distill_embed_retrieve_answer(self, tmp_path):
        service, _memory = _service()
        path = tmp_path / "receta.jsonl"
        path.write_text(
            json.dumps(
                {
                    "subject": "Patient",
                    "predicate": "has",
                    "object": "diabetes",
                    "metadata": {"source_file": "receta.pdf"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        count = await service.ingest_triples("user1", "doc1", str(path), gridfs_id="gridfs-receta")
        assert count == 1
        results = await service.semantic_search("diabetes", "user1")
        assert len(results) == 1
        context = await service.context_injection("diabetes", "user1")
        assert "diabetes" in context.lower()
        assert "receta.pdf" in context


class TestRAGHttp:
    def test_health(self):
        from main import create_app

        with (
            patch("main.document_store.connect", new_callable=AsyncMock),
            patch("main.document_store.close", new_callable=AsyncMock),
        ):
            client = TestClient(create_app())
            response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == "rag-service"

    def test_ingest_returns_201(self):
        from main import create_app

        with (
            patch("main.document_store.connect", new_callable=AsyncMock),
            patch("main.document_store.close", new_callable=AsyncMock),
            patch("main.rag_service.ingest_triples", new_callable=AsyncMock) as ingest,
        ):
            ingest.return_value = 15
            client = TestClient(create_app())
            response = client.post(
                "/ingest",
                json={
                    "user_id": "user1",
                    "doc_id": "abc-123",
                    "triples_path": "/data/triples/user1/abc-123.jsonl",
                    "gridfs_id": "grid-1",
                    "doc_type": "pdf",
                },
            )
        assert response.status_code == 201
        assert response.json()["triples_count"] == 15

    def test_get_document_wrong_user_is_404(self):
        from main import create_app

        with (
            patch("main.document_store.connect", new_callable=AsyncMock),
            patch("main.document_store.close", new_callable=AsyncMock),
            patch("main.rag_service.documents.get_document", new_callable=AsyncMock) as get_doc,
        ):
            get_doc.return_value = None
            client = TestClient(create_app())
            response = client.get("/documents/doc1", params={"user_id": "user-b"})
        assert response.status_code == 404

    def test_storage_and_delete_memory(self):
        from main import create_app

        with (
            patch("main.document_store.connect", new_callable=AsyncMock),
            patch("main.document_store.close", new_callable=AsyncMock),
            patch("main.rag_service.documents.storage_usage", new_callable=AsyncMock) as usage,
            patch("main.rag_service.delete_user_memory", new_callable=AsyncMock) as wipe,
        ):
            usage.return_value = {"bytes": 4096, "documents": 1}
            wipe.return_value = {"documents": 1, "embeddings": 3}
            client = TestClient(create_app())
            stored = client.get("/storage", params={"user_id": "user1"})
            removed = client.delete("/memory", params={"user_id": "user1"})
        assert stored.status_code == 200
        assert stored.json()["bytes"] == 4096
        assert removed.status_code == 200
        assert removed.json()["embeddings"] == 3


class TestEmbed:
    def test_embed_modalities_do_not_grow_the_collection(self):
        import base64

        from main import create_app
        from rag_service import rag_service

        store = MemoryVectorStore()
        rag_service._vector_store = store
        rag_service._embedder = None
        payload = base64.b64encode(b"bytes").decode()
        with (
            patch("main.document_store.connect", new_callable=AsyncMock),
            patch("main.document_store.close", new_callable=AsyncMock),
        ):
            client = TestClient(create_app())
            before = len(store.items)
            text = client.post(
                "/embed",
                headers={"X-Request-ID": "cid-embed"},
                json={"modality": "text", "text": "account suspended"},
            )
            image = client.post("/embed", json={"modality": "image", "content_base64": payload})
            with patch("embeddings.sample_video_frames", return_value=[b"frame-jpeg"]):
                video = client.post("/embed", json={"modality": "video", "content_base64": payload})
            blank = client.post("/embed", json={"modality": "text", "text": "  "})
        assert text.status_code == 200
        assert image.status_code == 200
        assert video.status_code == 200
        assert len(text.json()["vector"]) == 2048
        assert len(image.json()["vector"]) == 2048
        assert len(video.json()["vector"]) == 2048
        assert text.headers["X-Request-ID"] == "cid-embed"
        assert blank.status_code == 422
        assert len(store.items) == before
        assert store.items == []


# ── Embeddings coverage (embeddings.py) ───────────────────────────


class TestEmbeddingsCoverage:
    def test_l2_normalize(self):
        from embeddings import _l2_normalize

        result = _l2_normalize([3.0, 4.0])
        assert abs(result[0] - 0.6) < 0.001
        assert abs(result[1] - 0.8) < 0.001

    def test_l2_normalize_zero_vector(self):
        from embeddings import _l2_normalize

        result = _l2_normalize([0.0, 0.0])
        assert result == [0.0, 0.0]

    def test_fit_dim_same(self):
        from embeddings import _fit_dim

        result = _fit_dim([1.0, 2.0], 2)
        assert result == [1.0, 2.0]

    def test_fit_dim_truncate(self):
        from embeddings import _fit_dim

        result = _fit_dim([1.0, 2.0, 3.0, 4.0], 2)
        assert len(result) == 2

    def test_fit_dim_pad(self):
        from embeddings import _fit_dim

        result = _fit_dim([1.0], 3)
        assert len(result) == 3
        assert result[0] != 0.0

    def test_mock_embedder_text(self):
        from embeddings import MockEmbedder

        embedder = MockEmbedder(dim=2048)
        vector = embedder.embed_text("hello world")
        assert len(vector) == 2048
        assert any(v != 0.0 for v in vector)

    def test_mock_embedder_empty_text(self):
        from embeddings import MockEmbedder

        embedder = MockEmbedder(dim=2048)
        vector = embedder.embed_text("")
        assert len(vector) == 2048

    def test_mock_embedder_image(self):
        from embeddings import MockEmbedder

        embedder = MockEmbedder(dim=2048)
        vector = embedder.embed_image(b"fake image bytes")
        assert len(vector) == 2048

    def test_mock_embedder_video_averages_sampled_frames(self):
        from embeddings import MockEmbedder, _average_vectors

        embedder = MockEmbedder(dim=2048)
        frames = [b"start", b"middle", b"end"]
        with patch("embeddings.sample_video_frames", return_value=frames):
            vector = embedder.embed_video(b"fake video bytes")
        expected = _average_vectors([embedder.embed_image(frame) for frame in frames])
        assert vector == expected

    def test_mock_embedder_video_without_frames_is_none(self):
        from embeddings import MockEmbedder

        embedder = MockEmbedder(dim=2048)
        with patch("embeddings.sample_video_frames", return_value=[]):
            assert embedder.embed_video(b"fake video bytes") is None

    def test_timestamps_are_start_middle_and_end(self):
        from embeddings import _timestamps

        assert _timestamps(None) == [0.0]
        assert _timestamps(10.0) == [0.0, 5.0, 9.95]

    def test_sample_reads_start_middle_and_end_frames(self):
        from embeddings import sample_video_frames

        def fake_run(args, **_kwargs):
            result = MagicMock()
            result.returncode = 0
            if args[0] == "ffprobe":
                result.stdout = "10\n"
                return result
            stamp = args[args.index("-ss") + 1]
            result.stdout = f"jpeg-{stamp}".encode()
            return result

        with (
            patch("embeddings.shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("embeddings.subprocess.run", side_effect=fake_run),
        ):
            frames = sample_video_frames(b"\x00\x00\x00\x18ftypmp42")
        assert frames == [b"jpeg-0.000", b"jpeg-5.000", b"jpeg-9.950"]

    def test_sample_without_a_decoder_is_empty(self):
        from embeddings import sample_video_frames

        with patch("embeddings.shutil.which", return_value=None):
            assert sample_video_frames(b"\x00\x00\x00\x18ftypmp42") == []

    def test_create_embedder_mock(self):
        from embeddings import create_embedder

        embedder = create_embedder()
        assert hasattr(embedder, "embed_text")
        assert hasattr(embedder, "embed_image")
        assert hasattr(embedder, "embed_video")

    def test_embedder_protocol(self):
        from embeddings import Embedder, MockEmbedder

        embedder = MockEmbedder(dim=2048)
        assert isinstance(embedder, Embedder)


# ── Document Store coverage (document_store.py) ───────────────────


class TestDocumentStoreCoverage:
    def test_db_property_not_connected(self):
        from document_store import DocumentStore

        store = DocumentStore()
        with pytest.raises(RuntimeError, match="not connected"):
            _ = store.db

    def test_fs_property_not_connected(self):
        from document_store import DocumentStore

        store = DocumentStore()
        with pytest.raises(RuntimeError, match="not connected"):
            _ = store.fs

    @pytest.mark.asyncio
    async def test_close_without_connect(self):
        from document_store import DocumentStore

        store = DocumentStore()
        await store.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_get_binary_invalid_id(self):
        from document_store import DocumentStore

        store = DocumentStore()
        store._client = True  # Fake connected
        store._db = True
        store._fs = True
        result = await store.get_binary("invalid-id", "u1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_document_invalid_id(self):
        from document_store import DocumentStore

        store = DocumentStore()
        store._client = True
        store._db = MagicMock()
        store._fs = True
        result = await store.get_document("invalid", "u1")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_document_invalid_id(self):
        from document_store import DocumentStore

        store = DocumentStore()
        store._client = True
        store._db = MagicMock()
        store._fs = True
        result = await store.delete_document("invalid", "u1")
        assert result is False

    @pytest.mark.asyncio
    async def test_store_binary_success(self):
        from document_store import DocumentStore

        store = DocumentStore()
        mock_fs = MagicMock()
        mock_fs.upload_from_stream = AsyncMock(return_value="file-id-123")
        store._fs = mock_fs

        result = await store.store_binary(
            b"binary content",
            filename="test.pdf",
            user_id="user1",
            content_type="application/pdf",
        )
        assert result == "file-id-123"
        mock_fs.upload_from_stream.assert_awaited_once()
        call_kwargs = mock_fs.upload_from_stream.call_args
        assert call_kwargs[0][0] == "test.pdf"
        assert call_kwargs[0][1] == b"binary content"
        assert call_kwargs[1]["metadata"]["user_id"] == "user1"

    @pytest.mark.asyncio
    async def test_store_binary_pymongo_error(self):
        from document_store import DocumentStore, DocumentStoreError

        store = DocumentStore()
        mock_fs = MagicMock()
        mock_fs.upload_from_stream = AsyncMock(side_effect=PyMongoError("connection lost"))
        store._fs = mock_fs

        with pytest.raises(DocumentStoreError, match="GridFS upload failed"):
            await store.store_binary(
                b"data",
                filename="f.pdf",
                user_id="u1",
                content_type="pdf",
            )

    @pytest.mark.asyncio
    async def test_get_binary_success(self):
        from bson import ObjectId
        from document_store import DocumentStore

        store = DocumentStore()
        mock_fs = MagicMock()
        oid = ObjectId()
        mock_grid_out = MagicMock()
        mock_grid_out.metadata = {"user_id": "user1", "content_type": "pdf"}

        async def _aiter():
            yield b"chunk1"
            yield b"chunk2"

        mock_grid_out.__aiter__ = lambda self: _aiter()
        mock_fs.open_download_stream = AsyncMock(return_value=mock_grid_out)
        store._fs = mock_fs

        result = await store.get_binary(str(oid), "user1")
        assert result == b"chunk1chunk2"

    @pytest.mark.asyncio
    async def test_get_binary_wrong_user_id(self):
        from bson import ObjectId
        from document_store import DocumentStore

        store = DocumentStore()
        mock_fs = MagicMock()
        oid = ObjectId()
        mock_grid_out = MagicMock()
        mock_grid_out.metadata = {"user_id": "other_user"}
        mock_fs.open_download_stream = AsyncMock(return_value=mock_grid_out)
        store._fs = mock_fs

        result = await store.get_binary(str(oid), "user1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_binary_download_error(self):
        from bson import ObjectId
        from document_store import DocumentStore

        store = DocumentStore()
        mock_fs = MagicMock()
        oid = ObjectId()
        mock_fs.open_download_stream = AsyncMock(side_effect=Exception("not found"))
        store._fs = mock_fs

        result = await store.get_binary(str(oid), "user1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_binary_none_metadata(self):
        from bson import ObjectId
        from document_store import DocumentStore

        store = DocumentStore()
        mock_fs = MagicMock()
        oid = ObjectId()
        mock_grid_out = MagicMock()
        mock_grid_out.metadata = None
        mock_fs.open_download_stream = AsyncMock(return_value=mock_grid_out)
        store._fs = mock_fs

        result = await store.get_binary(str(oid), "user1")
        assert result is not None

    @pytest.mark.asyncio
    async def test_insert_document_with_content(self):
        from document_store import DocumentStore

        store = DocumentStore()
        mock_db = MagicMock()
        mock_fs = MagicMock()
        mock_db.documents.insert_one = AsyncMock(return_value=MagicMock(inserted_id="doc456"))
        mock_fs.upload_from_stream = AsyncMock(return_value="new-gridfs-id")
        store._db = mock_db
        store._fs = mock_fs

        doc_id = await store.insert_document(
            user_id="user1",
            doc_type="pdf",
            gridfs_id="old-id",
            triples_path="/data/triples.jsonl",
            content=b"file bytes",
            filename="test.pdf",
            content_type="application/pdf",
        )
        assert doc_id == "doc456"
        mock_fs.upload_from_stream.assert_awaited_once()
        payload = mock_db.documents.insert_one.call_args[0][0]
        assert payload["gridfs_id"] == "new-gridfs-id"

    @pytest.mark.asyncio
    async def test_insert_document_pymongo_error(self):
        from document_store import DocumentStore, DocumentStoreError

        store = DocumentStore()
        mock_db = MagicMock()
        mock_db.documents.insert_one = AsyncMock(side_effect=PyMongoError("write error"))
        store._db = mock_db

        with pytest.raises(DocumentStoreError, match="Document insert failed"):
            await store.insert_document(
                user_id="u1",
                doc_type="pdf",
                gridfs_id="g1",
                triples_path="/t.jsonl",
            )

    @pytest.mark.asyncio
    async def test_get_document_pymongo_error(self):
        from bson import ObjectId
        from document_store import DocumentStore

        store = DocumentStore()
        mock_db = MagicMock()
        mock_db.documents.find_one = AsyncMock(side_effect=PyMongoError("read error"))
        store._db = mock_db

        oid = ObjectId()
        result = await store.get_document(str(oid), "user1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_document_found(self):
        from bson import ObjectId
        from document_store import DocumentStore

        store = DocumentStore()
        mock_db = MagicMock()
        oid = ObjectId()
        mock_db.documents.find_one = AsyncMock(
            return_value={"_id": oid, "user_id": "user1", "type": "pdf"}
        )
        store._db = mock_db

        result = await store.get_document(str(oid), "user1")
        assert result is not None
        assert result["_id"] == str(oid)
        assert result["user_id"] == "user1"

    @pytest.mark.asyncio
    async def test_get_document_not_found(self):
        from bson import ObjectId
        from document_store import DocumentStore

        store = DocumentStore()
        mock_db = MagicMock()
        oid = ObjectId()
        mock_db.documents.find_one = AsyncMock(return_value=None)
        store._db = mock_db

        result = await store.get_document(str(oid), "user1")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_documents_pymongo_error(self):
        from document_store import DocumentStore, DocumentStoreError

        store = DocumentStore()
        mock_db = MagicMock()
        mock_db.documents.find.side_effect = PyMongoError("cursor error")
        store._db = mock_db

        with pytest.raises(DocumentStoreError, match="Document list failed"):
            await store.list_documents("user1")

    @pytest.mark.asyncio
    async def test_storage_usage_sums_raw_bytes(self):
        from bson import ObjectId
        from document_store import DocumentStore

        store = DocumentStore()
        file_id = ObjectId()
        mock_db = MagicMock()
        mock_db.documents.find.return_value = AsyncCursor(
            [{"_id": "doc1", "user_id": "user1", "gridfs_id": str(file_id)}]
        )
        files = MagicMock()
        files.find_one = AsyncMock(return_value={"_id": file_id, "length": 1200})
        mock_db.__getitem__.return_value = files
        store._db = mock_db

        usage = await store.storage_usage("user1")
        assert usage == {"bytes": 1200, "documents": 1}

    @pytest.mark.asyncio
    async def test_delete_document_success(self):
        from bson import ObjectId
        from document_store import DocumentStore

        store = DocumentStore()
        mock_db = MagicMock()
        mock_fs = MagicMock()
        oid = ObjectId()
        gridfs_oid = ObjectId()
        mock_db.documents.find_one = AsyncMock(
            return_value={"_id": oid, "user_id": "user1", "gridfs_id": str(gridfs_oid)}
        )
        mock_db.documents.delete_one = AsyncMock()
        mock_fs.delete = AsyncMock()
        store._db = mock_db
        store._fs = mock_fs

        result = await store.delete_document(str(oid), "user1")
        assert result is True
        mock_db.documents.delete_one.assert_awaited_once()
        mock_fs.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_document_not_found(self):
        from bson import ObjectId
        from document_store import DocumentStore

        store = DocumentStore()
        mock_db = MagicMock()
        mock_fs = MagicMock()
        oid = ObjectId()
        mock_db.documents.find_one = AsyncMock(return_value=None)
        mock_db.documents.delete_one = AsyncMock()
        store._db = mock_db
        store._fs = mock_fs

        result = await store.delete_document(str(oid), "user1")
        assert result is False
        mock_db.documents.delete_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_document_pymongo_error_on_delete(self):
        from bson import ObjectId
        from document_store import DocumentStore

        store = DocumentStore()
        mock_db = MagicMock()
        mock_fs = MagicMock()
        oid = ObjectId()
        gridfs_oid = ObjectId()
        mock_db.documents.find_one = AsyncMock(
            return_value={"_id": oid, "user_id": "user1", "gridfs_id": str(gridfs_oid)}
        )
        mock_db.documents.delete_one = AsyncMock(side_effect=PyMongoError("delete failed"))
        store._db = mock_db
        store._fs = mock_fs

        result = await store.delete_document(str(oid), "user1")
        assert result is False

    @pytest.mark.asyncio
    async def test_insert_document_defaults_filename_and_type(self):
        from document_store import DocumentStore

        store = DocumentStore()
        mock_db = MagicMock()
        mock_fs = MagicMock()
        mock_db.documents.insert_one = AsyncMock(return_value=MagicMock(inserted_id="doc789"))
        mock_fs.upload_from_stream = AsyncMock(return_value="gfs-default")
        store._db = mock_db
        store._fs = mock_fs

        await store.insert_document(
            user_id="u1",
            doc_type="pdf",
            gridfs_id="g1",
            triples_path="/t.jsonl",
            content=b"bytes",
        )
        call_kwargs = mock_fs.upload_from_stream.call_args
        assert call_kwargs[0][0] == "upload.bin"
        assert call_kwargs[1]["metadata"]["content_type"] == "pdf"

    @pytest.mark.asyncio
    async def test_delete_document_no_gridfs_id(self):
        from bson import ObjectId
        from document_store import DocumentStore

        store = DocumentStore()
        mock_db = MagicMock()
        mock_fs = MagicMock()
        oid = ObjectId()
        mock_db.documents.find_one = AsyncMock(return_value={"_id": oid, "user_id": "user1"})
        mock_db.documents.delete_one = AsyncMock()
        mock_fs.delete = AsyncMock()
        store._db = mock_db
        store._fs = mock_fs

        result = await store.delete_document(str(oid), "user1")
        assert result is True
        mock_fs.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_binary_empty_chunks(self):
        from bson import ObjectId
        from document_store import DocumentStore

        store = DocumentStore()
        mock_fs = MagicMock()
        oid = ObjectId()
        mock_grid_out = MagicMock()
        mock_grid_out.metadata = {"user_id": "user1"}

        async def _empty_iter():
            return
            yield  # pragma: no cover

        mock_grid_out.__aiter__ = lambda self: _empty_iter()
        mock_fs.open_download_stream = AsyncMock(return_value=mock_grid_out)
        store._fs = mock_fs

        result = await store.get_binary(str(oid), "user1")
        assert result == b""

    @pytest.mark.asyncio
    async def test_close_with_connected_client(self):
        from document_store import DocumentStore

        store = DocumentStore()
        mock_client = MagicMock()
        store._client = mock_client
        store._db = MagicMock()
        store._fs = MagicMock()

        await store.close()
        mock_client.close.assert_called_once()
        assert store._client is None
        assert store._db is None
        assert store._fs is None

    @pytest.mark.asyncio
    async def test_list_documents_converts_ids_to_strings(self):
        from bson import ObjectId
        from document_store import DocumentStore

        store = DocumentStore()
        mock_db = MagicMock()
        oid1 = ObjectId()
        oid2 = ObjectId()
        docs = [
            {"_id": oid1, "user_id": "u1", "type": "pdf"},
            {"_id": oid2, "user_id": "u1", "type": "html"},
        ]
        mock_db.documents.find.return_value = AsyncCursor(docs)
        store._db = mock_db

        result = await store.list_documents("u1")
        assert len(result) == 2
        assert result[0]["_id"] == str(oid1)
        assert result[1]["_id"] == str(oid2)
