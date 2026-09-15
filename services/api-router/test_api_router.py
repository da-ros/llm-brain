"""Tests for API Router — correlation ID, JWT, task status, upload flow."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from jose import jwt

os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["KAFKA_ENABLED"] = "false"
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("MONGODB_DB", "llm_brain_test")


def _isolate_service_imports() -> None:
    root = Path(__file__).resolve().parent
    prefixes = (
        "config",
        "main",
        "logging_setup",
        "exceptions",
        "pipeline",
        "lora",
        "providers",
        "routers",
    )
    for name in list(sys.modules):
        if name not in prefixes and not any(name.startswith(f"{item}.") for item in prefixes):
            continue
        mod_file = getattr(sys.modules[name], "__file__", None) or ""
        if mod_file and Path(mod_file).resolve().is_relative_to(root):
            continue
        del sys.modules[name]
    if str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))


_isolate_service_imports()

from config import clear_settings_cache, get_settings

clear_settings_cache()

from fastapi.testclient import TestClient
from kafka_io import apply_task_response, classify_response
from main import app
from rate_limit import limiter

SECRET = get_settings().JWT_SECRET_KEY
UUID_LEN = 36


def make_token(
    user_id: str = "user1", tier: str = "premium", *, use_frame1_claim: bool = False
) -> str:
    claim = "subscription_tier" if use_frame1_claim else "tier"
    return jwt.encode({"sub": user_id, claim: tier}, SECRET, algorithm="HS256")


def auth_header(user_id: str = "user1", tier: str = "premium", **kwargs) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(user_id, tier, **kwargs)}"}


@pytest.fixture
def tasks():
    store: dict[str, dict] = {}
    return store


@pytest.fixture
def client(tasks):
    limiter.reset()

    async def fake_connect():
        return None

    async def fake_disconnect():
        return None

    async def fake_indexes():
        return None

    async def fake_find(correlation_id: str):
        return tasks.get(correlation_id)

    async def fake_insert(document: dict):
        tasks[document["_id"]] = document

    async def fake_update(correlation_id: str, updates: dict):
        if correlation_id in tasks:
            tasks[correlation_id] = {**tasks[correlation_id], **updates}

    async def fake_save_upload(filename: str, content: bytes, content_type: str, user_id: str):
        return "gridfs-file-1"

    def fake_detect_mime(content: bytes, filename: str | None = None) -> str:
        name = (filename or "").lower()
        if name.endswith(".pdf"):
            return "application/pdf"
        if name.endswith(".txt"):
            return "text/plain"
        if name.endswith(".zip"):
            return "application/zip"
        return "application/octet-stream"

    with (
        patch("db.connect", fake_connect),
        patch("db.disconnect", fake_disconnect),
        patch("db.ensure_indexes", fake_indexes),
        patch("db.find_task", fake_find),
        patch("db.insert_task", fake_insert),
        patch("db.update_task", fake_update),
        patch("db.save_upload", fake_save_upload),
        patch("kafka_io.publish_file_uploaded") as publish,
        patch("kafka_io.publish_dlq") as publish_dlq,
        patch("routers.tasks.db.find_task", fake_find),
        patch("routers.upload.db.save_upload", fake_save_upload),
        patch("routers.upload.db.insert_task", fake_insert),
        patch("routers.upload.publish_file_uploaded", publish),
        patch("routers.upload.detect_mime", fake_detect_mime),
        TestClient(app) as test_client,
    ):
        test_client.publish = publish
        test_client.publish_dlq = publish_dlq
        yield test_client


# --- G.1 Correlation ID middleware ---


class TestCorrelationID:
    def test_generates_uuid_when_header_missing(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        correlation_id = response.headers.get("X-Request-ID")
        assert correlation_id is not None
        assert len(correlation_id) == UUID_LEN
        uuid.UUID(correlation_id)

    def test_propagates_provided_correlation_id(self, client):
        provided = "client-correlation-id-123"
        response = client.get("/health", headers={"X-Request-ID": provided})
        assert response.status_code == 200
        assert response.headers.get("X-Request-ID") == provided


# --- G.2 JWT verification ---


class TestJWTAuth:
    def test_health_is_public(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["service"] == "api-gateway"
        assert body["version"] == "0.1.0"
        assert "JWT_SECRET_KEY" not in body
        assert "secret" not in str(body).lower()

    def test_missing_token_returns_401(self, client):
        response = client.get("/tasks/any-id")
        assert response.status_code == 401

    def test_invalid_token_returns_401(self, client):
        response = client.get(
            "/tasks/any-id",
            headers={"Authorization": "Bearer not-a-jwt"},
        )
        assert response.status_code == 401

    def test_valid_token_extracts_user_and_tier(self, client, tasks):
        tasks["cid-1"] = {
            "_id": "cid-1",
            "user_id": "user1",
            "status": "in_progress",
            "retries": 0,
        }
        response = client.get("/tasks/cid-1", headers=auth_header())
        assert response.status_code == 200
        assert response.json()["status"] == "in_progress"

    def test_frame1_subscription_tier_claim(self, client, tasks):
        tasks["cid-1"] = {
            "_id": "cid-1",
            "user_id": "user1",
            "status": "success",
            "retries": 0,
            "result": {"triples_count": 3},
        }
        headers = auth_header(use_frame1_claim=True)
        response = client.get("/tasks/cid-1", headers=headers)
        assert response.status_code == 200
        assert response.json()["result"]["triples_count"] == 3


# --- G.3 Task status endpoint ---


class TestTaskStatus:
    def test_in_progress(self, client, tasks):
        tasks["abc"] = {
            "_id": "abc",
            "user_id": "user1",
            "status": "in_progress",
            "retries": 0,
        }
        response = client.get("/tasks/abc", headers=auth_header())
        assert response.status_code == 200
        assert response.json()["status"] == "in_progress"
        assert response.json()["retries"] == 0

    def test_success_includes_result(self, client, tasks):
        tasks["abc"] = {
            "_id": "abc",
            "user_id": "user1",
            "status": "success",
            "retries": 0,
            "result": {"triples_count": 15},
        }
        response = client.get("/tasks/abc", headers=auth_header())
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["result"]["triples_count"] == 15

    def test_error_includes_message(self, client, tasks):
        tasks["abc"] = {
            "_id": "abc",
            "user_id": "user1",
            "status": "error",
            "retries": 0,
            "error_message": "Unsupported file type",
        }
        response = client.get("/tasks/abc", headers=auth_header())
        assert response.status_code == 200
        assert response.json()["status"] == "error"
        assert response.json()["error_message"] == "Unsupported file type"

    def test_not_found(self, client):
        response = client.get("/tasks/missing", headers=auth_header())
        assert response.status_code == 404

    def test_other_users_task_forbidden(self, client, tasks):
        tasks["abc"] = {
            "_id": "abc",
            "user_id": "owner",
            "status": "in_progress",
            "retries": 0,
        }
        response = client.get("/tasks/abc", headers=auth_header(user_id="intruder"))
        assert response.status_code == 403


# --- Retry classification (C.3 / C.4) ---


class TestRetryLogic:
    def test_success(self):
        assert classify_response("success", 200, 0, 3) == "success"

    def test_5xx_retries_while_under_max(self):
        assert classify_response("error", 503, 0, 3) == "retry"
        assert classify_response("error", 500, 2, 3) == "retry"

    def test_5xx_dlq_at_max_retries(self):
        assert classify_response("error", 500, 3, 3) == "dlq-max"

    def test_4xx_and_3xx_do_not_retry(self):
        assert classify_response("error", 422, 0, 3) == "error"
        assert classify_response("error", 301, 0, 3) == "error"


# --- G.4 Integration: upload flow with Kafka mocked ---


class TestUploadFlow:
    def test_premium_upload_returns_202_and_publishes(self, client, tasks):
        response = client.post(
            "/api/upload",
            headers=auth_header(tier="premium"),
            files={"file": ("receta.pdf", b"%PDF-1.4 test", "application/pdf")},
        )
        assert response.status_code == 202
        body = response.json()
        correlation_id = body["correlation_id"]
        assert correlation_id
        assert body["status"] == "processing"
        assert correlation_id in tasks
        assert tasks[correlation_id]["status"] == "in_progress"
        assert tasks[correlation_id]["user_id"] == "user1"
        assert "expires_at" in tasks[correlation_id]
        client.publish.assert_called_once()
        published = client.publish.call_args.args[0]
        assert published["correlation_id"] == correlation_id
        assert published["file_id"] == "gridfs-file-1"

    def test_free_tier_upload_forbidden(self, client):
        response = client.post(
            "/api/upload",
            headers=auth_header(tier="free"),
            files={"file": ("receta.pdf", b"%PDF-1.4 test", "application/pdf")},
        )
        assert response.status_code == 403

    def test_invalid_file_type_unprocessable(self, client):
        response = client.post(
            "/api/upload",
            headers=auth_header(tier="premium"),
            files={"file": ("notes.zip", b"PK\x03\x04not-a-document", "application/zip")},
        )
        assert response.status_code == 422

    def test_plain_text_upload_accepted(self, client, tasks):
        response = client.post(
            "/api/upload",
            headers=auth_header(tier="premium"),
            files={"file": ("notes.txt", b"Patient has diabetes", "text/plain")},
        )
        assert response.status_code == 202
        assert response.json()["status"] == "processing"

    def test_file_too_large(self, client):
        from config import get_settings

        settings = get_settings()
        oversized = b"x" * (settings.MAX_UPLOAD_BYTES + 1)
        response = client.post(
            "/api/upload",
            headers=auth_header(tier="premium"),
            files={"file": ("big.pdf", oversized, "application/pdf")},
        )
        assert response.status_code == 413

    def test_upload_without_token_unauthorized(self, client):
        response = client.post(
            "/api/upload",
            files={"file": ("receta.pdf", b"%PDF-1.4 test", "application/pdf")},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_kafka_success_response_updates_task(self, tasks):
        tasks["abc-123"] = {
            "_id": "abc-123",
            "user_id": "user1",
            "status": "in_progress",
            "retries": 0,
            "max_retries": 3,
            "file_id": "gridfs-file-1",
            "filename": "receta.pdf",
            "content_type": "application/pdf",
            "service": "etl-service",
            "endpoint": "http://etl-service:8001/process",
        }

        async def fake_find(correlation_id: str):
            return tasks.get(correlation_id)

        async def fake_update(correlation_id: str, updates: dict):
            tasks[correlation_id] = {**tasks[correlation_id], **updates}

        with (
            patch("kafka_io.db.find_task", fake_find),
            patch("kafka_io.db.update_task", fake_update),
        ):
            await apply_task_response(
                {
                    "correlation_id": "abc-123",
                    "status": "success",
                    "http_code": 200,
                    "result": {"triples_count": 15},
                }
            )

        assert tasks["abc-123"]["status"] == "success"
        assert tasks["abc-123"]["result"]["triples_count"] == 15

    @pytest.mark.asyncio
    async def test_kafka_5xx_retries_and_republishes(self, tasks):
        tasks["abc-123"] = {
            "_id": "abc-123",
            "user_id": "user1",
            "status": "in_progress",
            "retries": 0,
            "max_retries": 3,
            "file_id": "gridfs-file-1",
            "filename": "receta.pdf",
            "content_type": "application/pdf",
            "service": "etl-service",
            "endpoint": "http://etl-service:8001/process",
        }

        async def fake_find(correlation_id: str):
            return tasks.get(correlation_id)

        async def fake_update(correlation_id: str, updates: dict):
            tasks[correlation_id] = {**tasks[correlation_id], **updates}

        with (
            patch("kafka_io.db.find_task", fake_find),
            patch("kafka_io.db.update_task", fake_update),
            patch("kafka_io.publish_file_uploaded") as republish,
        ):
            await apply_task_response(
                {
                    "correlation_id": "abc-123",
                    "status": "error",
                    "http_code": 503,
                    "error_message": "ETL unavailable",
                }
            )
            republish.assert_called_once()

        assert tasks["abc-123"]["status"] == "in_progress"
        assert tasks["abc-123"]["retries"] == 1

    @pytest.mark.asyncio
    async def test_kafka_4xx_marks_error_without_retry(self, tasks):
        tasks["abc-123"] = {
            "_id": "abc-123",
            "user_id": "user1",
            "status": "in_progress",
            "retries": 0,
            "max_retries": 3,
            "file_id": "gridfs-file-1",
            "filename": "notes.bin",
            "content_type": "application/octet-stream",
            "service": "etl-service",
            "endpoint": "http://etl-service:8001/process",
        }

        async def fake_find(correlation_id: str):
            return tasks.get(correlation_id)

        async def fake_update(correlation_id: str, updates: dict):
            tasks[correlation_id] = {**tasks[correlation_id], **updates}

        with (
            patch("kafka_io.db.find_task", fake_find),
            patch("kafka_io.db.update_task", fake_update),
            patch("kafka_io.publish_file_uploaded") as republish,
        ):
            await apply_task_response(
                {
                    "correlation_id": "abc-123",
                    "status": "error",
                    "http_code": 422,
                    "error_message": "Unsupported file type",
                }
            )
            republish.assert_not_called()

        assert tasks["abc-123"]["status"] == "error"

    @pytest.mark.asyncio
    async def test_kafka_max_retries_moves_to_dlq(self, tasks):
        tasks["abc-123"] = {
            "_id": "abc-123",
            "user_id": "user1",
            "status": "in_progress",
            "retries": 3,
            "max_retries": 3,
            "file_id": "gridfs-file-1",
            "filename": "receta.pdf",
            "content_type": "application/pdf",
            "service": "etl-service",
            "endpoint": "http://etl-service:8001/process",
        }

        async def fake_find(correlation_id: str):
            return tasks.get(correlation_id)

        async def fake_update(correlation_id: str, updates: dict):
            tasks[correlation_id] = {**tasks[correlation_id], **updates}

        with (
            patch("kafka_io.db.find_task", fake_find),
            patch("kafka_io.db.update_task", fake_update),
            patch("kafka_io.publish_dlq") as publish_dlq,
        ):
            await apply_task_response(
                {
                    "correlation_id": "abc-123",
                    "status": "error",
                    "http_code": 500,
                    "error_message": "OCR engine not available",
                }
            )
            publish_dlq.assert_called_once()

        assert tasks["abc-123"]["status"] == "dlq-max"


# --- Chat routing ---


class TestChat:
    def test_premium_chat_injects_rag_and_returns_200(self, client):
        with (
            patch("routers.chat._rag_context", new_callable=AsyncMock) as rag,
            patch("routers.chat._llm_generate", new_callable=AsyncMock) as llm,
        ):
            rag.return_value = ("diabetes notes", ["doc-1"])
            llm.return_value = "Insulin is a treatment."
            response = client.post(
                "/api/chat",
                headers=auth_header(tier="premium"),
                json={"message": "diabetes treatment", "use_rag": True},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["response"] == "Insulin is a treatment."
        assert body["context_used"] is True
        assert body["sources"] == ["doc-1"]
        assert body["correlation_id"]
        rag.assert_awaited()
        llm.assert_awaited()

    def test_free_chat_skips_rag(self, client):
        with (
            patch("routers.chat._rag_context", new_callable=AsyncMock) as rag,
            patch("routers.chat._llm_generate", new_callable=AsyncMock) as llm,
        ):
            llm.return_value = "Hello."
            response = client.post(
                "/api/chat",
                headers=auth_header(tier="free"),
                json={"message": "hi", "use_rag": True},
            )
        assert response.status_code == 200
        assert response.json()["context_used"] is False
        rag.assert_not_awaited()
        llm.assert_awaited()


def test_task_document_includes_ttl_expiry():
    from db import task_document

    doc = task_document(
        correlation_id="cid",
        user_id="user1",
        file_id="fid",
        filename="a.pdf",
        content_type="application/pdf",
    )
    assert doc["status"] == "in_progress"
    assert doc["max_retries"] == get_settings().MAX_RETRIES
    assert isinstance(doc["expires_at"], datetime)
    assert doc["expires_at"].tzinfo is UTC
    assert doc["expires_at"] > datetime.now(UTC)
