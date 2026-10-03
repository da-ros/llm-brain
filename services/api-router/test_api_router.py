"""Tests for API Router — correlation ID, JWT, task status, upload flow."""

from __future__ import annotations

import builtins
import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import jwt
import pytest

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
        "kafka_io",
        "db",
        "auth",
        "rate_limit",
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

import accounts
import db as api_db
import kafka_io as api_kafka
from fastapi import HTTPException
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


def _conversation_app():
    """In-process RAG conversation routes, so router tests forward over HTTP."""
    import importlib.util

    name = "rag_conversations_for_router_tests"
    if name not in sys.modules:
        path = Path(__file__).resolve().parents[1] / "rag" / "conversations.py"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        sys.modules[name] = module
        spec.loader.exec_module(module)
    else:
        module = sys.modules[name]
    module.reset_memory()
    module.bind(None)
    app = getattr(module, "_router_test_app", None)
    if app is None:
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(module.router)
        module._router_test_app = app
    return app


@pytest.fixture
def client(tasks):
    limiter.reset()
    accounts.reset_memory()
    transport = httpx.ASGITransport(app=_conversation_app())

    class _RagClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

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
        patch.object(api_db, "connect", fake_connect),
        patch.object(api_db, "disconnect", fake_disconnect),
        patch.object(api_db, "ensure_indexes", fake_indexes),
        patch.object(api_db, "find_task", fake_find),
        patch.object(api_db, "insert_task", fake_insert),
        patch.object(api_db, "update_task", fake_update),
        patch.object(api_db, "save_upload", fake_save_upload),
        patch.object(api_kafka, "publish_file_uploaded") as publish,
        patch.object(api_kafka, "publish_session_turn_completed") as publish_turn,
        patch("routers.chat.publish_session_turn_completed", publish_turn),
        patch.object(api_kafka, "publish_dlq") as publish_dlq,
        patch("routers.tasks.db.find_task", fake_find),
        patch("routers.upload.db.save_upload", fake_save_upload),
        patch("routers.upload.db.insert_task", fake_insert),
        patch("routers.upload.publish_file_uploaded", publish),
        patch("routers.upload.detect_mime", fake_detect_mime),
        patch("brain_client.httpx.AsyncClient", _RagClient),
        TestClient(app) as test_client,
    ):
        test_client.publish = publish
        test_client.publish_turn = publish_turn
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
            patch.object(api_db, "find_task", fake_find),
            patch.object(api_db, "update_task", fake_update),
            patch.object(api_kafka, "trigger_rag_ingest", new_callable=AsyncMock) as ingest,
        ):
            await apply_task_response(
                {
                    "correlation_id": "abc-123",
                    "status": "success",
                    "http_code": 200,
                    "result": {
                        "triples_count": 15,
                        "output_path": "/app/data/triples/user1/abc-123.jsonl",
                    },
                }
            )
            ingest.assert_awaited_once()

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
            patch.object(api_db, "find_task", fake_find),
            patch.object(api_db, "update_task", fake_update),
            patch.object(api_kafka, "publish_file_uploaded") as republish,
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
            patch.object(api_db, "find_task", fake_find),
            patch.object(api_db, "update_task", fake_update),
            patch.object(api_kafka, "publish_file_uploaded") as republish,
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
            patch.object(api_db, "find_task", fake_find),
            patch.object(api_db, "update_task", fake_update),
            patch.object(api_kafka, "publish_dlq") as publish_dlq,
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
    def test_premium_chat_uses_razonador_and_publishes_kafka(self, client):
        with patch("routers.chat._agents_reason", new_callable=AsyncMock) as reason:
            reason.return_value = {
                "response": "Insulin is a treatment.",
                "assumptions": [
                    "The answer is grounded in the user's retrieved personal documents."
                ],
                "sources": ["doc-1"],
                "tokens_used": 9,
                "session_id": "sess-1",
            }
            response = client.post(
                "/api/chat",
                headers=auth_header(tier="premium"),
                json={"message": "diabetes treatment", "use_rag": True},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["response"] == "Insulin is a treatment."
        assert body["assumptions"]
        assert body["sources"] == ["doc-1"]
        assert body["session_id"] == "sess-1"
        assert body["correlation_id"]
        reason.assert_awaited()
        client.publish_turn.assert_called_once()
        published = client.publish_turn.call_args.args[0]
        assert published["query"] == "diabetes treatment"
        assert published["user_id"] == "user1"
        assert published["correlation_id"] == body["correlation_id"]

    def test_free_chat_skips_agents_and_kafka(self, client):
        with (
            patch("routers.chat._agents_reason", new_callable=AsyncMock) as reason,
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
        assert response.json()["assumptions"] == []
        reason.assert_not_awaited()
        rag.assert_not_awaited()
        llm.assert_awaited()
        client.publish_turn.assert_not_called()

    def test_unauthenticated_chat_is_401(self, client):
        with patch("routers.chat._agents_reason", new_callable=AsyncMock) as reason:
            response = client.post("/api/chat", json={"message": "hi"})
        assert response.status_code == 401
        reason.assert_not_awaited()
        client.publish_turn.assert_not_called()

    def test_rollback_flag_uses_rag_llm_directly(self, client):
        settings = get_settings()
        original = settings.CHAT_VIA_AGENTS
        settings.CHAT_VIA_AGENTS = False
        try:
            with (
                patch("routers.chat._agents_reason", new_callable=AsyncMock) as reason,
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
        finally:
            settings.CHAT_VIA_AGENTS = original
        assert response.status_code == 200
        reason.assert_not_awaited()
        rag.assert_awaited()
        llm.assert_awaited()
        client.publish_turn.assert_not_called()


class TestSessionsEnd:
    def test_premium_session_end_accepted(self, client):
        with patch("routers.sessions.httpx.AsyncClient") as client_cls:
            instance = AsyncMock()
            response = MagicMock()
            response.status_code = 202
            response.json = MagicMock(return_value={"status": "accepted"})
            instance.post = AsyncMock(return_value=response)
            instance.__aenter__.return_value = instance
            instance.__aexit__.return_value = False
            client_cls.return_value = instance
            http_response = client.post(
                "/api/sessions/end",
                headers=auth_header(tier="premium"),
                json={"session_id": "sess-1"},
            )
        assert http_response.status_code == 202
        assert http_response.json()["session_id"] == "sess-1"

    def test_free_session_end_forbidden(self, client):
        response = client.post(
            "/api/sessions/end",
            headers=auth_header(tier="free"),
            json={"session_id": "sess-1"},
        )
        assert response.status_code == 403


class TestFineTuneTrigger:
    def test_manual_trigger_returns_202_with_job_id(self, client):
        with patch("routers.finetune.httpx.AsyncClient") as client_cls:
            instance = AsyncMock()
            response = MagicMock()
            response.status_code = 202
            response.json = MagicMock(return_value={"job_id": "ft-job-9", "status": "submitted"})
            instance.post = AsyncMock(return_value=response)
            instance.__aenter__.return_value = instance
            instance.__aexit__.return_value = False
            client_cls.return_value = instance
            http_response = client.post(
                "/api/finetune",
                headers=auth_header(tier="premium"),
                json={"batch_id": "batch-1"},
            )
        assert http_response.status_code == 202
        assert http_response.json()["job_id"] == "ft-job-9"

    def test_missing_batch_id_is_422(self, client):
        response = client.post(
            "/api/finetune",
            headers=auth_header(tier="premium"),
            json={},
        )
        assert response.status_code == 422

    def test_free_finetune_forbidden(self, client):
        response = client.post(
            "/api/finetune",
            headers=auth_header(tier="free"),
            json={"batch_id": "batch-1"},
        )
        assert response.status_code == 403


class TestLearning:
    def test_learning_adds_memory_count(self, client):
        with patch("routers.learning.httpx.AsyncClient") as client_cls:
            instance = AsyncMock()
            agents = MagicMock()
            agents.status_code = 200
            agents.json = MagicMock(
                return_value={
                    "interactions": 3,
                    "needed": 10,
                    "model_tag": "qwen3.5-4b-lora-v1",
                    "batch": {"id": "b1", "status": "ready", "items": 10, "needed": 10},
                    "job": None,
                    "learned": ["Prefer short answers."],
                    "cycles": [],
                }
            )
            rag = MagicMock()
            rag.status_code = 200
            rag.json = MagicMock(return_value={"documents": [{}, {}]})
            instance.get = AsyncMock(side_effect=[agents, rag])
            instance.__aenter__.return_value = instance
            instance.__aexit__.return_value = False
            client_cls.return_value = instance
            response = client.get("/api/learning", headers=auth_header())
        assert response.status_code == 200
        body = response.json()
        assert body["interactions"] == 3
        assert body["memories"] == 2
        assert body["model_tag"] == "qwen3.5-4b-lora-v1"
        assert body["batch"]["status"] == "ready"

    def test_free_learning_forbidden(self, client):
        response = client.get("/api/learning", headers=auth_header(tier="free"))
        assert response.status_code == 403


class TestDocuments:
    def test_get_document_404_when_rag_says_missing(self, client):
        with patch("routers.documents.httpx.AsyncClient") as client_cls:
            instance = AsyncMock()
            response = MagicMock()
            response.status_code = 404
            instance.get = AsyncMock(return_value=response)
            instance.__aenter__.return_value = instance
            instance.__aexit__.return_value = False
            client_cls.return_value = instance
            http_response = client.get(
                "/api/documents/doc-other",
                headers=auth_header(tier="premium"),
            )
        assert http_response.status_code == 404

    def _rag(self, documents: list[dict]):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"documents": documents}
        instance = AsyncMock()
        instance.get = AsyncMock(return_value=response)
        instance.__aenter__.return_value = instance
        instance.__aexit__.return_value = False
        return instance

    def test_search_matches_name_and_summary(self, client):
        docs = [
            {
                "_id": "doc-1",
                "filename": "acme-msa.pdf",
                "content_type": "application/pdf",
                "type": "text",
                "summary": "Payment terms for the Acme engagement",
                "created_at": "2026-03-15T00:00:00+00:00",
                "source_id": "task-1",
            },
            {
                "_id": "doc-2",
                "filename": "launch.png",
                "content_type": "image/png",
                "type": "image",
                "summary": "Screenshot of the launch board",
                "created_at": "2026-03-10T00:00:00+00:00",
            },
            {
                "_id": "doc-3",
                "filename": "budget.xlsx",
                "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "type": "text",
                "summary": "Quarterly budget",
                "created_at": "2026-03-09T00:00:00+00:00",
            },
        ]
        with patch("routers.documents.httpx.AsyncClient") as client_cls:
            client_cls.return_value = self._rag(docs)
            found = client.get(
                "/api/documents/search",
                headers=auth_header(),
                params={"q": "payment"},
            )
            listed = client.get("/api/documents", headers=auth_header())
        assert found.status_code == 200
        body = found.json()
        assert [row["name"] for row in body["documents"]] == ["acme-msa.pdf"]
        assert body["documents"][0]["status"] == "Embedded"
        assert "source_id" not in body["documents"][0]
        counts = listed.json()["counts"]
        assert counts == {"document": 2, "image": 1, "video": 0}
        sheet = next(row for row in listed.json()["documents"] if row["name"] == "budget.xlsx")
        assert sheet["kind"] == "document"

    def test_queue_and_distilled_are_separate_from_embedded(self, client):
        docs = [
            {
                "_id": "doc-1",
                "filename": "notes.md",
                "content_type": "text/markdown",
                "type": "text",
                "summary": "Meeting notes",
                "source_id": "done-task",
            }
        ]
        tasks = [
            {
                "_id": "done-task",
                "filename": "notes.md",
                "content_type": "text/markdown",
                "status": "success",
                "result": {"summary": "Meeting notes"},
            },
            {
                "_id": "queue-1",
                "filename": "review.mp4",
                "content_type": "video/mp4",
                "status": "in_progress",
            },
            {
                "_id": "facts-1",
                "filename": "plan.docx",
                "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "status": "success",
                "result": {"summary": "Scope and payment terms"},
            },
            {
                "_id": "audio-1",
                "filename": "voice.m4a",
                "content_type": "audio/mp4",
                "status": "success",
                "result": {"summary": "Spoken ideas"},
            },
        ]
        with (
            patch("routers.documents.httpx.AsyncClient") as client_cls,
            patch("routers.documents.list_user_tasks", new_callable=AsyncMock) as jobs,
        ):
            client_cls.return_value = self._rag(docs)
            jobs.return_value = tasks
            response = client.get("/api/documents", headers=auth_header())
        assert response.status_code == 200
        rows = {row["name"]: row for row in response.json()["documents"]}
        assert rows["notes.md"]["status"] == "Embedded"
        assert "done-task" not in rows
        assert rows["review.mp4"]["status"] == "Processing"
        assert rows["review.mp4"]["kind"] == "video"
        assert rows["plan.docx"]["status"] == "Distilled"
        assert rows["plan.docx"]["summary"] == "Scope and payment terms"
        assert "voice.m4a" not in rows
        assert response.json()["counts"] == {"document": 2, "image": 0, "video": 1}


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


class TestSimulate:
    """Premium what-if gateway: sync HTTP, no Kafka, 401/403/429, list isolation."""

    def _ok(self) -> dict:
        return {
            "simulation_id": "sim-1",
            "scenario_count": 3,
            "scenarios": [
                {
                    "id": "optimistic",
                    "title": "Rested",
                    "outcome": "Energy holds",
                    "assumptions": ["sleep stays at 8h"],
                    "trace": ["sleep_gte_7", "leaf:rested"],
                    "severity": "optimistic",
                },
                {
                    "id": "baseline",
                    "title": "Steady",
                    "outcome": "No change",
                    "assumptions": ["current sleep continues"],
                    "trace": ["sleep_eq_current", "leaf:sleep_baseline"],
                    "severity": "baseline",
                },
                {
                    "id": "pessimistic",
                    "title": "Drop",
                    "outcome": "Fatigue risk",
                    "assumptions": ["sleep falls"],
                    "trace": ["sleep_drop", "leaf:fatigue_risk"],
                    "severity": "pessimistic",
                },
            ],
            "assumptions": ["sleep stays at 8h"],
            "sources": [],
            "llm_used": True,
            "correlation_id": "cid",
        }

    def test_premium_simulate_returns_200_without_kafka(self, client):
        with patch("routers.simulate._simulator", new_callable=AsyncMock) as call:
            call.return_value = self._ok()
            response = client.post(
                "/api/simulate",
                headers={**auth_header(), "X-Request-ID": "cid-sim"},
                json={"question": "what if I sleep less", "variables": {"sleep_hours": 8}},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["llm_used"] is True
        assert body["scenario_count"] == 3
        client.publish_turn.assert_not_called()
        call.assert_awaited()
        assert call.await_args.args[0] == "POST"
        assert call.await_args.args[1] == "/simulate"
        assert call.await_args.kwargs["correlation_id"] == "cid-sim"
        forwarded = call.await_args.kwargs["json_body"]
        assert forwarded["user_id"] == "user1"
        assert forwarded["subscription_tier"] == "premium"
        assert forwarded["question"] == "what if I sleep less"

    def test_free_simulate_is_403(self, client):
        with patch("routers.simulate._simulator", new_callable=AsyncMock) as call:
            response = client.post(
                "/api/simulate",
                headers=auth_header(tier="free"),
                json={"question": "what if I sleep less"},
            )
        assert response.status_code == 403
        call.assert_not_awaited()
        client.publish_turn.assert_not_called()

    def test_missing_jwt_is_401(self, client):
        with patch("routers.simulate._simulator", new_callable=AsyncMock) as call:
            response = client.post("/api/simulate", json={"question": "what if I sleep less"})
        assert response.status_code == 401
        call.assert_not_awaited()

    def test_eleventh_simulate_is_429(self, client):
        with patch("routers.simulate._simulator", new_callable=AsyncMock) as call:
            call.return_value = self._ok()
            headers = auth_header()
            for _ in range(10):
                ok = client.post(
                    "/api/simulate",
                    headers=headers,
                    json={"question": "what if I sleep less"},
                )
                assert ok.status_code == 200
            blocked = client.post(
                "/api/simulate",
                headers=headers,
                json={"question": "what if I sleep less"},
            )
        assert blocked.status_code == 429
        assert call.await_count == 10
        client.publish_turn.assert_not_called()

    def test_list_and_get_are_isolated(self, client):
        stored = self._ok()

        async def fake(method, path, **kwargs):
            user_id = (kwargs.get("params") or {}).get("user_id")
            if method == "GET" and path == "/simulations":
                if user_id == "user1":
                    return {"simulations": [stored]}
                return {"simulations": []}
            if method == "GET" and path.startswith("/simulations/"):
                if user_id != "user1":
                    raise HTTPException(status_code=404, detail="Not found")
                return stored
            return stored

        with patch("routers.simulate._simulator", new=fake):
            listed = client.get("/api/simulations", headers=auth_header())
            own = client.get("/api/simulations/sim-1", headers=auth_header())
            hidden = client.get("/api/simulations/sim-1", headers=auth_header("user2"))
            other_list = client.get("/api/simulations", headers=auth_header("user2"))
        assert listed.status_code == 200
        assert listed.json()["simulations"][0]["simulation_id"] == "sim-1"
        assert own.status_code == 200
        assert own.json()["scenarios"][0]["trace"]
        assert hidden.status_code == 404
        assert other_list.status_code == 200
        assert other_list.json()["simulations"] == []
        client.publish_turn.assert_not_called()


class TestShield:
    """Premium scan gateway: sync HTTP, no Kafka, 401/403/429, Frame 7 list."""

    def _ok(self) -> dict:
        return {
            "alert": True,
            "likelihood": 0.9,
            "severity": "high",
            "summary": "Likely scam",
            "reasons": [{"type": "llm", "id": "llm", "detail": "rationale"}],
            "llm_used": True,
            "incident_id": "inc-1",
        }

    def test_premium_scan_and_incidents_shape(self, client):
        with patch("routers.shield._shield", new_callable=AsyncMock) as call:
            call.return_value = self._ok()
            scanned = client.post(
                "/api/shield/scan",
                headers={**auth_header(), "X-Request-ID": "cid-shield"},
                json={"text": "act now", "source": "email"},
            )
            call.return_value = {
                "incidents": [
                    {
                        "id": "inc-1",
                        "created_at": "2026-09-24T00:00:00",
                        "severity": "high",
                        "summary": "Likely scam",
                        "source": "email",
                    }
                ]
            }
            listed = client.get("/api/shield/incidents", headers=auth_header())
        assert scanned.status_code == 200
        assert scanned.json()["alert"] is True
        assert scanned.json()["likelihood"] == 0.9
        assert scanned.json()["reasons"]
        assert listed.status_code == 200
        item = listed.json()["incidents"][0]
        assert set(item) >= {"id", "created_at", "severity", "summary", "source"}
        client.publish_turn.assert_not_called()
        assert call.await_args_list[0].kwargs["correlation_id"] == "cid-shield"
        assert call.await_args_list[0].args[1] == "/scan"

    def test_free_and_missing_jwt(self, client):
        with patch("routers.shield._shield", new_callable=AsyncMock) as call:
            free = client.post(
                "/api/shield/scan",
                headers=auth_header(tier="free"),
                json={"text": "act now", "source": "sms"},
            )
            missing = client.post("/api/shield/scan", json={"text": "act now", "source": "sms"})
            free_list = client.get("/api/shield/incidents", headers=auth_header(tier="free"))
        assert free.status_code == 403
        assert missing.status_code == 401
        assert free_list.status_code == 403
        call.assert_not_awaited()

    def test_thirty_first_scan_is_429(self, client):
        with patch("routers.shield._shield", new_callable=AsyncMock) as call:
            call.return_value = self._ok()
            headers = auth_header()
            for _ in range(30):
                ok = client.post(
                    "/api/shield/scan",
                    headers=headers,
                    json={"text": "act now", "source": "email"},
                )
                assert ok.status_code == 200
            blocked = client.post(
                "/api/shield/scan",
                headers=headers,
                json={"text": "act now", "source": "email"},
            )
        assert blocked.status_code == 429
        assert call.await_count == 30
        client.publish_turn.assert_not_called()

    def test_guidelines_and_empty_incidents(self, client):
        with patch("routers.shield._shield", new_callable=AsyncMock) as call:
            call.side_effect = [
                {"text": "Assistive only. Multimodal LLM reasoning on test text."},
                {"incidents": []},
            ]
            guide = client.get("/api/shield/guidelines", headers=auth_header())
            empty = client.get("/api/shield/incidents", headers=auth_header())
        assert guide.status_code == 200
        assert guide.json()["text"]
        assert empty.status_code == 200
        assert empty.json()["incidents"] == []
        client.publish_turn.assert_not_called()


# ── Kafka IO coverage (kafka_io.py) ───────────────────────────────


class TestClassifyResponse:
    def test_success(self):
        assert classify_response("success", None, 0, 3) == "success"

    def test_retry_under_max(self):
        assert classify_response("error", 500, 1, 3) == "retry"

    def test_dlq_max(self):
        assert classify_response("error", 500, 3, 3) == "dlq-max"

    def test_error_4xx(self):
        assert classify_response("error", 422, 0, 3) == "error"

    def test_error_no_http_code(self):
        assert classify_response("error", None, 0, 3) == "error"


class TestFileUploadedMessage:
    def test_builds_message(self):
        from kafka_io import file_uploaded_message

        task = {
            "_id": "cid-1",
            "user_id": "u1",
            "file_id": "fid-1",
            "filename": "test.pdf",
            "content_type": "application/pdf",
        }
        msg = file_uploaded_message(task)
        assert msg["correlation_id"] == "cid-1"
        assert msg["user_id"] == "u1"
        assert msg["file_id"] == "fid-1"
        assert msg["service"] == "etl-service"

    def test_defaults(self):
        from kafka_io import file_uploaded_message

        task = {"_id": "cid-2"}
        msg = file_uploaded_message(task)
        assert msg["service"] == "etl-service"
        assert "endpoint" in msg


class TestPublishFunctions:
    def test_publish_session_turn_completed(self):
        from kafka_io import publish_session_turn_completed

        mock_producer = MagicMock()
        with patch("kafka_io._producer", return_value=mock_producer):
            publish_session_turn_completed({"correlation_id": "c1", "query": "q"})
        mock_producer.send.assert_called_once()
        mock_producer.flush.assert_called_once()
        mock_producer.close.assert_called_once()

    def test_publish_file_uploaded(self):
        from kafka_io import publish_file_uploaded

        mock_producer = MagicMock()
        with patch("kafka_io._producer", return_value=mock_producer):
            publish_file_uploaded({"correlation_id": "c1", "filename": "f.pdf"})
        mock_producer.send.assert_called_once()
        mock_producer.flush.assert_called_once()
        mock_producer.close.assert_called_once()

    def test_publish_dlq(self):
        from kafka_io import publish_dlq

        mock_producer = MagicMock()
        with patch("kafka_io._producer", return_value=mock_producer):
            publish_dlq({"correlation_id": "c1", "status": "dlq-max"})
        mock_producer.send.assert_called_once()
        mock_producer.flush.assert_called_once()
        mock_producer.close.assert_called_once()


class TestTriggerRagIngest:
    @pytest.mark.asyncio
    async def test_no_user_id_skips(self):
        from kafka_io import trigger_rag_ingest

        await trigger_rag_ingest({}, None, "cid-1")  # Should not raise

    @pytest.mark.asyncio
    async def test_success(self):
        from kafka_io import trigger_rag_ingest

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"triples_count": 5}
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch("kafka_io.httpx.AsyncClient", return_value=mock_client):
            await trigger_rag_ingest(
                {"user_id": "u1", "file_id": "f1", "content_type": "pdf"},
                None,
                "cid-1",
            )

    @pytest.mark.asyncio
    async def test_with_output_path(self):
        from kafka_io import trigger_rag_ingest

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"triples_count": 3}
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch("kafka_io.httpx.AsyncClient", return_value=mock_client):
            await trigger_rag_ingest(
                {"user_id": "u1", "file_id": "f1"},
                {"output_path": "/custom/path.jsonl"},
                "cid-1",
            )

    @pytest.mark.asyncio
    async def test_http_error_skips(self):
        from kafka_io import trigger_rag_ingest

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch("kafka_io.httpx.AsyncClient", return_value=mock_client):
            await trigger_rag_ingest(
                {"user_id": "u1", "file_id": "f1"},
                None,
                "cid-1",
            )

    @pytest.mark.asyncio
    async def test_connection_error_skips(self):
        from kafka_io import trigger_rag_ingest

        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch("kafka_io.httpx.AsyncClient", return_value=mock_client):
            await trigger_rag_ingest(
                {"user_id": "u1", "file_id": "f1"},
                None,
                "cid-1",
            )


class TestApplyTaskResponse:
    @pytest.mark.asyncio
    async def test_missing_correlation_id(self):
        from kafka_io import apply_task_response

        await apply_task_response({})  # Should not raise

    @pytest.mark.asyncio
    async def test_task_not_found(self):
        from kafka_io import apply_task_response

        with patch("kafka_io.db") as mock_db:
            mock_db.find_task = AsyncMock(return_value=None)
            await apply_task_response({"correlation_id": "cid-1"})

    @pytest.mark.asyncio
    async def test_success_action(self):
        from kafka_io import apply_task_response

        task = {
            "_id": "cid-1",
            "user_id": "u1",
            "file_id": "f1",
            "retries": 0,
            "max_retries": 3,
        }
        with (
            patch("kafka_io.db") as mock_db,
            patch("kafka_io.trigger_rag_ingest", new_callable=AsyncMock),
        ):
            mock_db.find_task = AsyncMock(return_value=task)
            mock_db.update_task = AsyncMock()
            await apply_task_response(
                {
                    "correlation_id": "cid-1",
                    "status": "success",
                    "result": {"output_path": "/path.jsonl"},
                }
            )
            mock_db.update_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_action(self):
        from kafka_io import apply_task_response

        task = {
            "_id": "cid-1",
            "user_id": "u1",
            "file_id": "f1",
            "retries": 0,
            "max_retries": 3,
        }
        with patch("kafka_io.db") as mock_db, patch("kafka_io.publish_file_uploaded"):
            mock_db.find_task = AsyncMock(return_value=task)
            mock_db.update_task = AsyncMock()
            await apply_task_response(
                {
                    "correlation_id": "cid-1",
                    "status": "error",
                    "http_code": 500,
                    "error_message": "server error",
                }
            )
            mock_db.update_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_dlq_max_action(self):
        from kafka_io import apply_task_response

        task = {
            "_id": "cid-1",
            "user_id": "u1",
            "file_id": "f1",
            "retries": 3,
            "max_retries": 3,
        }
        with patch("kafka_io.db") as mock_db, patch("kafka_io.publish_dlq"):
            mock_db.find_task = AsyncMock(return_value=task)
            mock_db.update_task = AsyncMock()
            await apply_task_response(
                {
                    "correlation_id": "cid-1",
                    "status": "error",
                    "http_code": 500,
                    "error_message": "permanent failure",
                }
            )
            mock_db.update_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_action(self):
        from kafka_io import apply_task_response

        task = {
            "_id": "cid-1",
            "user_id": "u1",
            "file_id": "f1",
            "retries": 0,
            "max_retries": 3,
        }
        with patch("kafka_io.db") as mock_db:
            mock_db.find_task = AsyncMock(return_value=task)
            mock_db.update_task = AsyncMock()
            await apply_task_response(
                {
                    "correlation_id": "cid-1",
                    "status": "error",
                    "http_code": 422,
                    "error_message": "bad request",
                }
            )
            mock_db.update_task.assert_called_once()


class TestConsumerThread:
    def test_stop_consumer_thread(self):
        from kafka_io import stop_consumer_thread

        stop_consumer_thread()  # Should not raise


# ── MIME utility coverage (mimeutil.py) ──────────────────────────


class TestDetectMime:
    """Tests for detect_mime() covering python-magic detection and fallback paths."""

    def test_magic_available_returns_detected_mime(self):
        """When python-magic is available, detect_mime uses it."""
        from mimeutil import detect_mime

        mock_magic = MagicMock()
        mock_magic.from_buffer.return_value = "application/pdf"

        with patch.dict("sys.modules", {"magic": mock_magic}):
            result = detect_mime(b"%PDF-1.4 content", filename="test.pdf")
        assert result == "application/pdf"
        mock_magic.from_buffer.assert_called_once_with(b"%PDF-1.4 content", mime=True)

    def test_magic_available_strips_parameters(self):
        """Magic result with parameters (charset, etc.) is stripped."""
        from mimeutil import detect_mime

        mock_magic = MagicMock()
        mock_magic.from_buffer.return_value = "text/plain; charset=utf-8"

        with patch.dict("sys.modules", {"magic": mock_magic}):
            result = detect_mime(b"hello world")
        assert result == "text/plain"

    def test_magic_unavailable_falls_back_to_mimetypes(self):
        """When python-magic import gives None, falls back to mimetypes.guess_type."""
        from mimeutil import detect_mime

        with patch.dict("sys.modules", {"magic": None}):
            result = detect_mime(b"content", filename="document.pdf")
        assert result == "application/pdf"

    def test_magic_exception_falls_back_to_mimetypes(self):
        """When magic.from_buffer raises, falls back to mimetypes."""
        from mimeutil import detect_mime

        mock_magic = MagicMock()
        mock_magic.from_buffer.side_effect = Exception("magic error")

        with patch.dict("sys.modules", {"magic": mock_magic}):
            result = detect_mime(b"content", filename="image.png")
        assert result == "image/png"

    def test_no_magic_no_filename_returns_octet_stream(self):
        """Without magic and no filename, returns application/octet-stream."""
        from mimeutil import detect_mime

        with patch.dict("sys.modules", {"magic": None}):
            result = detect_mime(b"\x00\x01\x02\x03")
        assert result == "application/octet-stream"

    def test_no_magic_unknown_extension_returns_octet_stream(self):
        """Fallback to mimetypes returns octet-stream for unknown extensions."""
        from mimeutil import detect_mime

        with patch.dict("sys.modules", {"magic": None}):
            result = detect_mime(b"data", filename="file.xyzunknown")
        assert result == "application/octet-stream"

    def test_magic_returns_empty_falls_back(self):
        """If magic returns empty string, falls through to filename fallback."""
        from mimeutil import detect_mime

        mock_magic = MagicMock()
        mock_magic.from_buffer.return_value = ""

        with patch.dict("sys.modules", {"magic": mock_magic}):
            result = detect_mime(b"content", filename="notes.txt")
        assert result == "text/plain"

    def test_magic_returns_none_falls_back(self):
        """If magic returns None/falsy, falls through to filename fallback."""
        from mimeutil import detect_mime

        mock_magic = MagicMock()
        mock_magic.from_buffer.return_value = None

        with patch.dict("sys.modules", {"magic": mock_magic}):
            result = detect_mime(b"content", filename="page.html")
        assert result == "text/html"

    def test_filename_fallback_strips_parameters(self):
        """mimetypes.guess_type result with parameters is stripped."""
        from mimeutil import detect_mime

        with (
            patch.dict("sys.modules", {"magic": None}),
            patch(
                "mimeutil.mimetypes.guess_type",
                return_value=("text/html; charset=utf-8", None),
            ),
        ):
            result = detect_mime(b"<html>", filename="page.html")
        assert result == "text/html"

    def test_filename_fallback_no_match_returns_octet_stream(self):
        """mimetypes returns None for unknown type -> octet-stream."""
        from mimeutil import detect_mime

        with (
            patch.dict("sys.modules", {"magic": None}),
            patch(
                "mimeutil.mimetypes.guess_type",
                return_value=(None, None),
            ),
        ):
            result = detect_mime(b"data", filename="file.unknownext")
        assert result == "application/octet-stream"

    def test_magic_module_import_error_falls_back(self):
        """ModuleNotFoundError during import magic is caught and falls back."""
        from mimeutil import detect_mime

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "magic":
                raise ImportError("No module named 'magic'")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            result = detect_mime(b"content", filename="doc.pdf")
        assert result == "application/pdf"

    def test_filename_only_no_magic(self):
        """With no magic, filename-only path returns guessed MIME."""
        from mimeutil import detect_mime

        with patch.dict("sys.modules", {"magic": None}):
            result = detect_mime(b"content", filename="photo.jpeg")
        assert result == "image/jpeg"


class TestIsAllowedUploadMime:
    """Tests for is_allowed_upload_mime() covering all branches."""

    def test_pdf_allowed(self):
        from mimeutil import is_allowed_upload_mime

        assert is_allowed_upload_mime("application/pdf") is True

    def test_image_png_allowed(self):
        from mimeutil import is_allowed_upload_mime

        assert is_allowed_upload_mime("image/png") is True

    def test_image_jpeg_allowed(self):
        from mimeutil import is_allowed_upload_mime

        assert is_allowed_upload_mime("image/jpeg") is True

    def test_video_mp4_allowed(self):
        from mimeutil import is_allowed_upload_mime

        assert is_allowed_upload_mime("video/mp4") is True

    def test_video_webm_allowed(self):
        from mimeutil import is_allowed_upload_mime

        assert is_allowed_upload_mime("video/webm") is True

    def test_unknown_mime_not_allowed(self):
        from mimeutil import is_allowed_upload_mime

        assert is_allowed_upload_mime("application/zip") is False

    def test_empty_string_not_allowed(self):
        from mimeutil import is_allowed_upload_mime

        assert is_allowed_upload_mime("") is False

    def test_none_not_allowed(self):
        from mimeutil import is_allowed_upload_mime

        assert is_allowed_upload_mime(None) is False

    def test_mimetype_with_charset_still_allowed(self):
        from mimeutil import is_allowed_upload_mime

        assert is_allowed_upload_mime("application/pdf; charset=utf-8") is True

    def test_case_insensitive(self):
        from mimeutil import is_allowed_upload_mime

        assert is_allowed_upload_mime("Application/PDF") is True

    def test_text_plain_allowed(self):
        from mimeutil import is_allowed_upload_mime

        assert is_allowed_upload_mime("text/plain") is True

    def test_docx_allowed(self):
        from mimeutil import is_allowed_upload_mime

        assert (
            is_allowed_upload_mime(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            is True
        )

    def test_video_quicktime_allowed(self):
        from mimeutil import is_allowed_upload_mime

        assert is_allowed_upload_mime("video/quicktime") is True

    def test_non_video_unknown_not_allowed(self):
        from mimeutil import is_allowed_upload_mime

        assert is_allowed_upload_mime("application/x-executable") is False

    def test_whitespace_around_mime_stripped(self):
        from mimeutil import is_allowed_upload_mime

        assert is_allowed_upload_mime("  video/webm  ") is True


class TestSupportedTypesMessage:
    def test_returns_nonempty_string(self):
        from mimeutil import supported_types_message

        msg = supported_types_message()
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_mentions_key_types(self):
        from mimeutil import supported_types_message

        msg = supported_types_message()
        assert "pdf" in msg
        assert "image" in msg
        assert "video" in msg
        assert "text/plain" in msg


# ── db.py unit tests ──────────────────────────────────────────────


class TestDbConnectDisconnect:
    """Cover connect() (lines 24-29) and disconnect() (lines 35-38)."""

    @pytest.mark.asyncio
    async def test_connect_creates_motor_client(self):
        import motor.motor_asyncio  # noqa: F401 — ensure submodule is loaded

        with patch("motor.motor_asyncio.AsyncIOMotorClient") as motor_cls:
            mock_client = MagicMock()
            motor_cls.return_value = mock_client

            await api_db.connect()

            assert motor_cls.called
            assert api_db._client is mock_client
            assert api_db._database is not None

        # Clean up
        api_db._client = None
        api_db._database = None

        # Clean up
        api_db._client = None
        api_db._database = None

    @pytest.mark.asyncio
    async def test_disconnect_closes_client(self):
        mock_client = MagicMock()
        api_db._client = mock_client
        api_db._database = MagicMock()

        await api_db.disconnect()

        mock_client.close.assert_called_once()
        assert api_db._client is None
        assert api_db._database is None

    @pytest.mark.asyncio
    async def test_disconnect_when_already_none(self):
        api_db._client = None
        api_db._database = None
        await api_db.disconnect()  # Should not raise

    @pytest.mark.asyncio
    async def test_disconnect_resets_globals(self):
        """Verify both _client and _database are set to None after disconnect."""
        mock_client = MagicMock()
        api_db._client = mock_client
        api_db._database = MagicMock()
        await api_db.disconnect()
        assert api_db._client is None
        assert api_db._database is None
        mock_client.close.assert_called_once()


class TestDbHelper:
    """Cover _db() (lines 42-44)."""

    def test_db_raises_when_not_connected(self):
        saved = api_db._database
        api_db._database = None
        try:
            with pytest.raises(RuntimeError, match="MongoDB is not connected"):
                api_db._db()
        finally:
            api_db._database = saved

    def test_db_returns_database(self):
        saved = api_db._database
        mock_db = MagicMock()
        api_db._database = mock_db
        try:
            assert api_db._db() is mock_db
        finally:
            api_db._database = saved


class TestEnsureIndexes:
    """Cover ensure_indexes() (lines 49-50)."""

    @pytest.mark.asyncio
    async def test_ensure_indexes_calls_create_index(self):
        mock_db = MagicMock()
        mock_task_status = MagicMock()
        mock_task_status.create_index = AsyncMock()
        mock_db.task_status = mock_task_status

        saved = api_db._database
        api_db._database = mock_db
        try:
            await api_db.ensure_indexes()
            mock_task_status.create_index.assert_awaited_once_with(
                "expires_at", expireAfterSeconds=0
            )
        finally:
            api_db._database = saved


class TestSaveUpload:
    """Cover save_upload() (lines 86-94)."""

    @pytest.mark.asyncio
    async def test_save_upload_uses_gridfs_bucket(self):
        import motor.motor_asyncio  # noqa: F401 — ensure submodule is loaded

        mock_db = MagicMock()
        mock_bucket_instance = MagicMock()
        mock_bucket_instance.upload_from_stream = AsyncMock(return_value="file-object-id-123")

        saved = api_db._database
        api_db._database = mock_db
        try:
            with patch(
                "motor.motor_asyncio.AsyncIOMotorGridFSBucket", return_value=mock_bucket_instance
            ) as bucket_cls:
                result = await api_db.save_upload(
                    filename="receta.pdf",
                    content=b"fake-content",
                    content_type="application/pdf",
                    user_id="user1",
                )
                bucket_cls.assert_called_once_with(mock_db)
                mock_bucket_instance.upload_from_stream.assert_awaited_once()
                call_args = mock_bucket_instance.upload_from_stream.call_args
                assert call_args.args[0] == "receta.pdf"
                assert call_args.kwargs["metadata"]["content_type"] == "application/pdf"
                assert call_args.kwargs["metadata"]["user_id"] == "user1"
                assert result == "file-object-id-123"
        finally:
            api_db._database = saved

    @pytest.mark.asyncio
    async def test_save_upload_defaults_filename(self):
        import motor.motor_asyncio  # noqa: F401 — ensure submodule is loaded

        mock_db = MagicMock()
        mock_bucket_instance = MagicMock()
        mock_bucket_instance.upload_from_stream = AsyncMock(return_value="fid-2")

        saved = api_db._database
        api_db._database = mock_db
        try:
            with patch(
                "motor.motor_asyncio.AsyncIOMotorGridFSBucket", return_value=mock_bucket_instance
            ):
                result = await api_db.save_upload(
                    filename="",
                    content=b"data",
                    content_type="text/plain",
                    user_id="u2",
                )
                call_args = mock_bucket_instance.upload_from_stream.call_args
                assert call_args.args[0] == "upload.bin"
                assert result == "fid-2"
        finally:
            api_db._database = saved


class TestInsertTask:
    """Cover insert_task() (line 98)."""

    @pytest.mark.asyncio
    async def test_insert_task_calls_insert_one(self):
        mock_db = MagicMock()
        mock_db.task_status.insert_one = AsyncMock()

        saved = api_db._database
        api_db._database = mock_db
        try:
            doc = {"_id": "cid-1", "user_id": "u1", "status": "in_progress"}
            await api_db.insert_task(doc)
            mock_db.task_status.insert_one.assert_awaited_once_with(doc)
        finally:
            api_db._database = saved


class TestFindTask:
    """Cover find_task() (line 102)."""

    @pytest.mark.asyncio
    async def test_find_task_returns_document(self):
        mock_db = MagicMock()
        expected = {"_id": "cid-1", "status": "success"}
        mock_db.task_status.find_one = AsyncMock(return_value=expected)

        saved = api_db._database
        api_db._database = mock_db
        try:
            result = await api_db.find_task("cid-1")
            mock_db.task_status.find_one.assert_awaited_once_with({"_id": "cid-1"})
            assert result == expected
        finally:
            api_db._database = saved

    @pytest.mark.asyncio
    async def test_find_task_returns_none(self):
        mock_db = MagicMock()
        mock_db.task_status.find_one = AsyncMock(return_value=None)

        saved = api_db._database
        api_db._database = mock_db
        try:
            result = await api_db.find_task("missing-id")
            assert result is None
        finally:
            api_db._database = saved


class TestUpdateTask:
    """Cover update_task() (lines 106-107)."""

    @pytest.mark.asyncio
    async def test_update_task_sets_updated_at(self):
        mock_db = MagicMock()
        mock_db.task_status.update_one = AsyncMock()

        saved = api_db._database
        api_db._database = mock_db
        try:
            await api_db.update_task("cid-1", {"status": "success", "retries": 1})
            mock_db.task_status.update_one.assert_awaited_once()
            call_args = mock_db.task_status.update_one.call_args
            assert call_args.args[0] == {"_id": "cid-1"}
            payload = call_args.args[1]["$set"]
            assert payload["status"] == "success"
            assert payload["retries"] == 1
            assert "updated_at" in payload
            assert isinstance(payload["updated_at"], datetime)
            assert payload["updated_at"].tzinfo is UTC
        finally:
            api_db._database = saved

    @pytest.mark.asyncio
    async def test_update_task_empty_updates(self):
        mock_db = MagicMock()
        mock_db.task_status.update_one = AsyncMock()

        saved = api_db._database
        api_db._database = mock_db
        try:
            await api_db.update_task("cid-1", {})
            call_args = mock_db.task_status.update_one.call_args
            payload = call_args.args[1]["$set"]
            assert "updated_at" in payload
            assert len(payload) == 1  # only updated_at
        finally:
            api_db._database = saved


class TestTaskDocument:
    """Cover task_document() more thoroughly."""

    def test_all_fields_present(self):
        from db import task_document

        doc = task_document(
            correlation_id="cid-x",
            user_id="user-x",
            file_id="fid-x",
            filename="doc.pdf",
            content_type="application/pdf",
        )
        assert doc["_id"] == "cid-x"
        assert doc["user_id"] == "user-x"
        assert doc["file_id"] == "fid-x"
        assert doc["filename"] == "doc.pdf"
        assert doc["content_type"] == "application/pdf"
        assert doc["service"] == "etl-service"
        assert doc["retries"] == 0
        assert doc["http_code"] is None
        assert doc["error_message"] is None
        assert doc["result"] is None
        assert doc["endpoint"].endswith("/process")

    def test_created_at_and_updated_at_are_equal(self):
        from db import task_document

        doc = task_document(
            correlation_id="c",
            user_id="u",
            file_id="f",
            filename="a.txt",
            content_type="text/plain",
        )
        assert doc["created_at"] == doc["updated_at"]

    def test_ttl_days_matches_settings(self):
        from datetime import timedelta

        from db import task_document

        settings = get_settings()
        doc = task_document(
            correlation_id="c",
            user_id="u",
            file_id="f",
            filename="a.txt",
            content_type="text/plain",
        )
        expected_expires = doc["created_at"] + timedelta(days=settings.TASK_STATUS_TTL_DAYS)
        assert doc["expires_at"] == expected_expires


class TestAnalytics:
    """Premium analytics gateway: sync HTTP, no Kafka, 401/403/429."""

    def _ok(self) -> dict:
        return {
            "rows_upserted": 2,
            "llm_used": True,
            "correlations": {
                "sleep_productivity": {
                    "r": 1.0,
                    "n": 2,
                    "status": "ok",
                    "points": [{"date": "2026-01-01", "x": 6, "y": 4}],
                },
                "meetings_focus": {"r": None, "n": 1, "status": "insufficient", "points": []},
            },
            "insights": {"narrative": "Sleep tracks productivity.", "llm_used": True},
        }

    def test_premium_ingest_and_correlations(self, client):
        with patch("routers.analytics._analytics", new_callable=AsyncMock) as call:
            call.return_value = self._ok()
            ingested = client.post(
                "/api/analytics/ingest",
                headers={**auth_header(), "X-Request-ID": "cid-analytics"},
                files={"file": ("diary.csv", b"date,sleep_hours\n2026-01-01,6\n", "text/csv")},
            )
            call.return_value = {
                "narrative": "Sleep tracks productivity.",
                "llm_used": True,
                "pairs": self._ok()["correlations"],
            }
            listed = client.get("/api/analytics/correlations", headers=auth_header())
        assert ingested.status_code == 200
        assert ingested.json()["rows_upserted"] == 2
        assert ingested.json()["llm_used"] is True
        assert listed.status_code == 200
        assert listed.json()["pairs"]["sleep_productivity"]["r"] == 1.0
        assert listed.json()["narrative"]
        client.publish.assert_not_called()
        client.publish_turn.assert_not_called()
        assert call.await_args_list[0].kwargs["correlation_id"] == "cid-analytics"
        assert call.await_args_list[0].args[1] == "/ingest"

    def test_free_and_missing_jwt(self, client):
        with patch("routers.analytics._analytics", new_callable=AsyncMock) as call:
            free = client.post(
                "/api/analytics/ingest",
                headers=auth_header(tier="free"),
                files={"file": ("diary.csv", b"a", "text/csv")},
            )
            missing = client.post(
                "/api/analytics/ingest",
                files={"file": ("diary.csv", b"a", "text/csv")},
            )
            free_read = client.get(
                "/api/analytics/correlations",
                headers=auth_header(tier="free"),
            )
            free_metrics = client.get("/api/analytics/metrics", headers=auth_header(tier="free"))
        assert free.status_code == 403
        assert missing.status_code == 401
        assert free_read.status_code == 403
        assert free_metrics.status_code == 403
        call.assert_not_awaited()

    def test_eleventh_ingest_is_429(self, client):
        with patch("routers.analytics._analytics", new_callable=AsyncMock) as call:
            call.return_value = self._ok()
            headers = auth_header()
            files = {"file": ("diary.csv", b"date\n2026-01-01\n", "text/csv")}
            for _ in range(10):
                ok = client.post("/api/analytics/ingest", headers=headers, files=files)
                assert ok.status_code == 200
            blocked = client.post("/api/analytics/ingest", headers=headers, files=files)
        assert blocked.status_code == 429
        assert call.await_count == 10
        client.publish.assert_not_called()

    def test_thirty_first_correlation_is_429(self, client):
        with patch("routers.analytics._analytics", new_callable=AsyncMock) as call:
            call.return_value = {
                "narrative": "Sleep tracks productivity.",
                "llm_used": True,
                "pairs": self._ok()["correlations"],
            }
            headers = auth_header("user-corr")
            for _ in range(30):
                ok = client.get("/api/analytics/correlations", headers=headers)
                assert ok.status_code == 200
            blocked = client.get("/api/analytics/correlations", headers=headers)
        assert blocked.status_code == 429
        assert call.await_count == 30

    def test_cross_user_metric_is_404(self, client):
        with patch("routers.analytics._analytics", new_callable=AsyncMock) as call:
            call.side_effect = HTTPException(status_code=404, detail="Not found")
            hidden = client.get("/api/analytics/metrics/metric-other", headers=auth_header())
        assert hidden.status_code == 404
        call.assert_awaited()


class TestBrain:
    def test_new_chat_is_a_thread(self, client):
        created = client.post("/api/chats", headers=auth_header())
        assert created.status_code == 201
        assert created.json()["title"] == "New chat"
        chat_id = created.json()["id"]
        listed = client.get("/api/chats", headers=auth_header())
        assert listed.json()["chats"][0]["id"] == chat_id
        hidden = client.get("/api/chats", headers=auth_header("user2"))
        assert hidden.json()["chats"] == []

    def test_turns_stay_on_the_chat(self, client):
        created = client.post("/api/chats", headers=auth_header())
        chat_id = created.json()["id"]
        today = datetime.now().date().isoformat()
        client.put(
            f"/api/calendar/{today}",
            headers=auth_header(),
            json={"note": "Launch review"},
        )
        with (
            patch("routers.chat._agents_reason", new_callable=AsyncMock) as reason,
            patch("routers.chat._rag_context", new_callable=AsyncMock) as rag,
            patch("routers.chat._llm_generate", new_callable=AsyncMock) as llm,
        ):
            rag.return_value = ("notes", ["Acme MSA"])
            llm.return_value = "Finish the draft."
            posted = client.post(
                "/api/chat",
                headers=auth_header(),
                json={"message": "What is due?", "session_id": chat_id, "use_rag": True},
            )
        assert posted.status_code == 200
        listed = client.get(f"/api/chats/{chat_id}/turns", headers=auth_header())
        assert listed.status_code == 200
        turns = listed.json()["turns"]
        assert turns[0] == {"role": "user", "text": "What is due?", "cards": [], "assumptions": []}
        assert turns[1]["role"] == "assistant"
        assert turns[1]["text"] == "Finish the draft."
        assert turns[1]["cards"][0]["origin"] == "memory"
        reason.assert_not_awaited()
        hidden = client.get(f"/api/chats/{chat_id}/turns", headers=auth_header("user2"))
        assert hidden.status_code == 404

    def test_free_chat_uses_one_file_without_memory_or_rag(self, client):
        created = client.post("/api/chats", headers=auth_header(tier="free"))
        chat_id = created.json()["id"]
        with (
            patch("routers.chat.load_attachment", return_value="clause 4") as load,
            patch("routers.chat._rag_context", new_callable=AsyncMock) as rag,
            patch("routers.chat._llm_generate", new_callable=AsyncMock) as llm,
            patch("db.save_upload", new_callable=AsyncMock) as save,
        ):
            llm.return_value = "From the file."
            response = client.post(
                "/api/chat",
                headers=auth_header(tier="free"),
                json={
                    "message": "What does it say?",
                    "session_id": chat_id,
                    "use_rag": True,
                    "attachment_filename": "notes.docx",
                    "attachment_base64": "bm90ZXM=",
                },
            )
        assert response.status_code == 200
        assert response.json()["context_used"] is False
        assert response.json()["sources"] == []
        assert response.json()["source_cards"] == [
            {"n": 1, "label": "notes.docx", "origin": "attachment"},
        ]
        rag.assert_not_awaited()
        save.assert_not_awaited()
        load.assert_called_once()
        prompt = llm.await_args.kwargs["prompt"]
        assert "clause 4" in prompt
        assert "not saved to memory" in prompt
        stored = client.get(f"/api/chats/{chat_id}/turns", headers=auth_header(tier="free"))
        assert stored.json()["turns"][1]["text"] == "From the file."

    def test_free_chat_accepts_five_files_and_rejects_six(self, client):
        files = [
            {"filename": f"note-{index}.txt", "content_base64": "bm90ZXM="}
            for index in range(5)
        ]
        with (
            patch("routers.chat.load_attachment", side_effect=lambda name, _data: name),
            patch("routers.chat._rag_context", new_callable=AsyncMock) as rag,
            patch("routers.chat._llm_generate", new_callable=AsyncMock) as llm,
            patch("db.save_upload", new_callable=AsyncMock) as save,
        ):
            llm.return_value = "From the files."
            accepted = client.post(
                "/api/chat",
                headers=auth_header(tier="free"),
                json={"message": "Compare these.", "use_rag": True, "attachments": files},
            )
            rejected = client.post(
                "/api/chat",
                headers=auth_header(tier="free"),
                json={
                    "message": "Too many.",
                    "attachments": files + [{"filename": "extra.txt", "content_base64": "bm90ZXM="}],
                },
            )
        assert accepted.status_code == 200
        assert accepted.json()["context_used"] is False
        assert [card["label"] for card in accepted.json()["source_cards"]] == [
            f"note-{index}.txt" for index in range(5)
        ]
        prompt = llm.await_args.kwargs["prompt"]
        assert "note-0.txt" in prompt and "note-4.txt" in prompt
        rag.assert_not_awaited()
        save.assert_not_awaited()
        assert rejected.status_code == 422

    def test_next_question_includes_earlier_files(self, client):
        created = client.post("/api/chats", headers=auth_header(tier="free"))
        chat_id = created.json()["id"]
        with (
            patch("routers.chat.load_attachment", return_value="clause 4"),
            patch("routers.chat._rag_context", new_callable=AsyncMock) as rag,
            patch("routers.chat._llm_generate", new_callable=AsyncMock) as llm,
            patch("db.save_upload", new_callable=AsyncMock) as save,
        ):
            llm.side_effect = ["First answer.", "Second answer."]
            first = client.post(
                "/api/chat",
                headers=auth_header(tier="free"),
                json={
                    "message": "What is due?",
                    "session_id": chat_id,
                    "attachment_filename": "notes.docx",
                    "attachment_base64": "bm90ZXM=",
                },
            )
            second = client.post(
                "/api/chat",
                headers=auth_header(tier="free"),
                json={"message": "What changed?", "session_id": chat_id},
            )
        assert first.status_code == 200
        assert second.status_code == 200
        prompt = llm.await_args.kwargs["prompt"]
        assert "Earlier in this chat" in prompt
        assert "clause 4" in prompt
        assert "First answer." in prompt
        assert "What changed?" in prompt
        rag.assert_not_awaited()
        save.assert_not_awaited()
        stored = client.get(f"/api/chats/{chat_id}/turns", headers=auth_header(tier="free"))
        assert "clause 4" not in stored.text

    def test_premium_follow_up_sends_earlier_files_to_agents(self, client):
        created = client.post("/api/chats", headers=auth_header())
        chat_id = created.json()["id"]
        with (
            patch("routers.chat.load_attachment", return_value="clause 4"),
            patch("routers.chat._agents_reason", new_callable=AsyncMock) as reason,
            patch("routers.chat._llm_generate", new_callable=AsyncMock) as llm,
        ):
            llm.return_value = "First answer."
            reason.return_value = {
                "response": "Still due.",
                "assumptions": [],
                "sources": [],
                "tokens_used": 1,
                "session_id": chat_id,
            }
            first = client.post(
                "/api/chat",
                headers=auth_header(),
                json={
                    "message": "What is due?",
                    "session_id": chat_id,
                    "attachment_filename": "notes.docx",
                    "attachment_base64": "bm90ZXM=",
                },
            )
            second = client.post(
                "/api/chat",
                headers=auth_header(),
                json={"message": "What changed?", "session_id": chat_id},
            )
        assert first.status_code == 200
        assert second.status_code == 200
        reason.assert_awaited()
        message = reason.await_args.kwargs["message"]
        assert "clause 4" in message
        assert "First answer." in message
        assert "What changed?" in message

    def test_free_calendar_and_memory_are_forbidden(self, client):
        today = datetime.now().date().isoformat()
        saved = client.put(
            f"/api/calendar/{today}",
            headers=auth_header(tier="free"),
            json={"note": "Ship the draft"},
        )
        listed = client.get(
            "/api/calendar",
            headers=auth_header(tier="free"),
            params={"start": today, "end": today},
        )
        documents = client.get("/api/documents", headers=auth_header(tier="free"))
        assert saved.status_code == 403
        assert listed.status_code == 403
        assert documents.status_code == 403

    def test_calendar_notes_stay_with_the_owner(self, client):
        today = datetime.now().date().isoformat()
        saved = client.put(
            f"/api/calendar/{today}",
            headers=auth_header(),
            json={"note": "Ship the draft"},
        )
        assert saved.status_code == 200
        visible = client.get(
            "/api/calendar",
            headers=auth_header(),
            params={"start": today, "end": today},
        )
        assert visible.json()["notes"] == [{"date": today, "note": "Ship the draft"}]
        hidden = client.get(
            "/api/calendar",
            headers=auth_header("user2"),
            params={"start": today, "end": today},
        )
        assert hidden.json()["notes"] == []

    def test_attachment_is_used_once_and_not_saved(self, client):
        with (
            patch("routers.chat.load_attachment", return_value="clause 4") as load,
            patch("routers.chat._agents_reason", new_callable=AsyncMock) as reason,
            patch("routers.chat._rag_context", new_callable=AsyncMock) as rag,
            patch("routers.chat._llm_generate", new_callable=AsyncMock) as llm,
            patch("db.save_upload", new_callable=AsyncMock) as save,
        ):
            rag.return_value = ("msa notes", ["Acme MSA"])
            llm.return_value = "Finish the draft."
            response = client.post(
                "/api/chat",
                headers=auth_header(),
                json={
                    "message": "What is due?",
                    "attachment_filename": "notes.docx",
                    "attachment_base64": "bm90ZXM=",
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["response"] == "Finish the draft."
        assert body["sources"] == ["Acme MSA"]
        assert body["source_cards"] == [
            {"n": 1, "label": "Acme MSA", "origin": "memory"},
            {"n": 2, "label": "notes.docx", "origin": "attachment"},
        ]
        reason.assert_not_awaited()
        save.assert_not_awaited()
        load.assert_called_once()
        prompt = llm.await_args.kwargs["prompt"]
        assert "What is due?" in prompt
        assert "clause 4" in prompt
        assert "not saved to memory" in prompt
        published = client.publish_turn.call_args.args[0]
        assert published["query"] == "What is due?"
        assert "clause 4" not in published["query"]

    def test_calendar_note_is_numbered_with_memory(self, client):
        today = datetime.now().date().isoformat()
        client.put(
            f"/api/calendar/{today}",
            headers=auth_header(),
            json={"note": "Launch review"},
        )
        with (
            patch("routers.chat._agents_reason", new_callable=AsyncMock) as reason,
            patch("routers.chat._rag_context", new_callable=AsyncMock) as rag,
            patch("routers.chat._llm_generate", new_callable=AsyncMock) as llm,
        ):
            rag.return_value = ("notes", ["Product notes", "Acme MSA"])
            llm.return_value = "Prepare the review."
            response = client.post(
                "/api/chat",
                headers=auth_header(),
                json={"message": "this week"},
            )
        assert response.status_code == 200
        cards = response.json()["source_cards"]
        assert [card["n"] for card in cards] == [1, 2, 3]
        assert cards[0]["origin"] == "memory"
        assert cards[1]["origin"] == "memory"
        assert cards[2]["origin"] == "calendar"
        assert "Launch review" in llm.await_args.kwargs["prompt"]
        reason.assert_not_awaited()

    def test_every_source_is_numbered(self, client):
        today = datetime.now().date().isoformat()
        client.put(
            f"/api/calendar/{today}",
            headers=auth_header(),
            json={"note": "Launch review"},
        )
        with (
            patch("routers.chat.load_attachment", return_value="section 2") as load,
            patch("routers.chat._rag_context", new_callable=AsyncMock) as rag,
            patch("routers.chat._llm_generate", new_callable=AsyncMock) as llm,
        ):
            rag.return_value = ("notes", ["One", "Two", "Three", "Four"])
            llm.return_value = "All four."
            response = client.post(
                "/api/chat",
                headers=auth_header(),
                json={
                    "message": "this week",
                    "attachment_filename": "plan.pdf",
                    "attachment_base64": "bm90ZXM=",
                },
            )
        assert response.status_code == 200
        cards = response.json()["source_cards"]
        assert [card["n"] for card in cards] == [1, 2, 3, 4, 5, 6]
        assert [card["origin"] for card in cards] == [
            "memory",
            "memory",
            "memory",
            "memory",
            "calendar",
            "attachment",
        ]
        assert cards[-1]["label"] == "plan.pdf"
        load.assert_called_once()

    def test_unsupported_attachment_is_422(self, client):
        with patch("routers.chat._agents_reason", new_callable=AsyncMock) as reason:
            response = client.post(
                "/api/chat",
                headers=auth_header(),
                json={
                    "message": "hi",
                    "attachment_filename": "notes.zip",
                    "attachment_base64": "cGRm",
                },
            )
        assert response.status_code == 422
        reason.assert_not_awaited()
        client.publish_turn.assert_not_called()


class TestAccount:
    def test_signup_signin_and_plan(self, client):
        created = client.post(
            "/api/auth/signup",
            json={
                "name": "Ada Lovelace",
                "email": "ada@example.com",
                "password": "password1",
                "plan": "premium",
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert body["user"]["name"] == "Ada Lovelace"
        assert body["user"]["plan"] == "premium"
        token = body["access_token"]
        account = client.get("/api/account", headers={"Authorization": f"Bearer {token}"})
        assert account.status_code == 200
        assert account.json()["email"] == "ada@example.com"

        duplicate = client.post(
            "/api/auth/signup",
            json={
                "name": "Ada",
                "email": "ada@example.com",
                "password": "password1",
            },
        )
        assert duplicate.status_code == 409

        signed = client.post(
            "/api/auth/signin",
            json={"email": "ada@example.com", "password": "password1"},
        )
        assert signed.status_code == 200
        wrong = client.post(
            "/api/auth/signin",
            json={"email": "ada@example.com", "password": "nope-nope"},
        )
        assert wrong.status_code == 401

        changed = client.patch(
            "/api/account",
            headers={"Authorization": f"Bearer {token}"},
            json={"plan": "free"},
        )
        assert changed.status_code == 200
        assert changed.json()["user"]["plan"] == "free"
        refreshed = client.get(
            "/api/account",
            headers={"Authorization": f"Bearer {changed.json()['access_token']}"},
        )
        assert refreshed.json()["plan"] == "free"

    def test_short_password_is_422(self, client):
        response = client.post(
            "/api/auth/signup",
            json={"name": "Ada", "email": "ada@example.com", "password": "short"},
        )
        assert response.status_code == 422

    def test_status_marks_each_service(self, client):
        llm_url = get_settings().LLM_SERVICE_URL

        async def fake_get(url, *args, **kwargs):
            response = MagicMock()
            response.status_code = 200 if str(url).startswith(llm_url) else 503
            return response

        with patch("routers.account.httpx.AsyncClient") as client_cls:
            instance = AsyncMock()
            instance.get = fake_get
            instance.__aenter__.return_value = instance
            instance.__aexit__.return_value = False
            client_cls.return_value = instance
            response = client.get("/api/status", headers=auth_header())
        assert response.status_code == 200
        services = {row["id"]: row for row in response.json()["services"]}
        assert services["llm"]["label"] == "LLM core"
        assert services["llm"]["status"] == "online"
        assert services["personal"]["label"] == "Personal model"
        assert services["personal"]["status"] == "offline"
        assert set(services) == {"llm", "memory", "personal", "analytics", "agents", "shield"}

    def test_storage_reports_document_bytes(self, client):
        with patch("routers.account.httpx.AsyncClient") as client_cls:
            instance = AsyncMock()
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {"bytes": 2048, "documents": 2}
            instance.get = AsyncMock(return_value=response)
            instance.__aenter__.return_value = instance
            instance.__aexit__.return_value = False
            client_cls.return_value = instance
            http_response = client.get("/api/storage", headers=auth_header())
        assert http_response.status_code == 200
        assert http_response.json() == {"bytes": 2048, "documents": 2}

    def test_delete_data_clears_rag_memory_and_uploads(self, client):
        with (
            patch("routers.account.httpx.AsyncClient") as client_cls,
            patch("routers.account.delete_user_uploads", new_callable=AsyncMock) as uploads,
        ):
            instance = AsyncMock()
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {"documents": 2, "embeddings": 5}
            instance.delete = AsyncMock(return_value=response)
            instance.__aenter__.return_value = instance
            instance.__aexit__.return_value = False
            client_cls.return_value = instance
            uploads.return_value = 1
            http_response = client.delete("/api/data", headers=auth_header())
        assert http_response.status_code == 200
        assert http_response.json() == {"documents": 2, "embeddings": 5, "uploads": 1}
        uploads.assert_awaited_once()


def _write_pack(directory: Path, pack_id: str, tier: str, payload: bytes, user_id: str | None = None, sha: str | None = None) -> dict:
    import hashlib
    import json

    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{pack_id}.pte"
    (directory / filename).write_bytes(payload)
    body = {
        "id": pack_id,
        "family": "Qwen3.5-4B",
        "tier": tier,
        "quantization": "Q4",
        "parameters": "4.0B",
        "filename": filename,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest() if sha is None else sha,
    }
    if user_id:
        body["user_id"] = user_id
    (directory / "manifest.json").write_text(json.dumps(body), encoding="utf-8")
    return body


class TestOnDeviceModels:
    def test_free_download_is_base_and_ignores_tier_query(self, client, tmp_path):
        settings = get_settings()
        settings.ONDEVICE_MODEL_DIR = str(tmp_path)
        _write_pack(tmp_path / "base", "qwen3.5-4b-base-q4", "free", b"base-weights")
        _write_pack(tmp_path / "users" / "user1", "qwen3.5-4b-finetuned-q4", "premium", b"lora-weights", "user1")
        meta = client.get("/api/models/on-device?tier=premium", headers=auth_header(tier="free"))
        assert meta.status_code == 200
        assert meta.json()["id"] == "qwen3.5-4b-base-q4"
        assert meta.json()["ready"] is True
        assert meta.json()["quantization"] == "Q4"
        downloaded = client.get(
            "/api/models/on-device/file",
            headers={**auth_header(tier="free"), "X-Request-ID": "corr-model"},
        )
        assert downloaded.status_code == 200
        assert downloaded.content == b"base-weights"
        assert b"lora-weights" not in downloaded.content

    def test_premium_missing_pack_is_404_and_not_base(self, client, tmp_path):
        get_settings().ONDEVICE_MODEL_DIR = str(tmp_path)
        _write_pack(tmp_path / "base", "qwen3.5-4b-base-q4", "free", b"base-weights")
        meta = client.get("/api/models/on-device", headers=auth_header(tier="premium"))
        assert meta.status_code == 200
        assert meta.json()["id"] == "qwen3.5-4b-finetuned-q4"
        assert meta.json()["ready"] is False
        assert meta.json()["sha256"] == ""
        missing = client.get("/api/models/on-device/file", headers=auth_header(tier="premium"))
        assert missing.status_code == 404
        assert missing.content != b"base-weights"

    def test_premium_user_cannot_read_another_users_pack(self, client, tmp_path):
        get_settings().ONDEVICE_MODEL_DIR = str(tmp_path)
        own = _write_pack(
            tmp_path / "users" / "user-a",
            "qwen3.5-4b-finetuned-q4",
            "premium",
            b"user-a-weights",
            "user-a",
        )
        meta = client.get("/api/models/on-device", headers=auth_header("user-b", tier="premium"))
        assert meta.json()["ready"] is False
        assert own["sha256"] not in meta.text
        downloaded = client.get("/api/models/on-device/file", headers=auth_header("user-b", tier="premium"))
        assert downloaded.status_code == 404
        assert b"user-a-weights" not in downloaded.content

    def test_manifest_sha_is_returned_without_reading_the_weight(self, client, tmp_path):
        get_settings().ONDEVICE_MODEL_DIR = str(tmp_path)
        published = "ab" * 32
        _write_pack(tmp_path / "base", "qwen3.5-4b-base-q4", "free", b"base-weights", sha=published)
        meta = client.get("/api/models/on-device", headers=auth_header(tier="free"))
        assert meta.json()["ready"] is True
        assert meta.json()["sha256"] == published
        downloaded = client.get("/api/models/on-device/file", headers=auth_header(tier="free"))
        assert downloaded.status_code == 200
        assert downloaded.content == b"base-weights"

    def test_size_mismatch_is_not_ready(self, client, tmp_path):
        get_settings().ONDEVICE_MODEL_DIR = str(tmp_path)
        written = _write_pack(tmp_path / "base", "qwen3.5-4b-base-q4", "free", b"base-weights")
        manifest_path = tmp_path / "base" / "manifest.json"
        written["bytes"] = written["bytes"] + 1
        manifest_path.write_text(json.dumps(written), encoding="utf-8")
        meta = client.get("/api/models/on-device", headers=auth_header(tier="free"))
        assert meta.json()["ready"] is False
        assert client.get("/api/models/on-device/file", headers=auth_header(tier="free")).status_code == 404

    def test_model_routes_require_a_token_and_health_stays_public(self, client):
        assert client.get("/api/models/on-device").status_code == 401
        assert client.get("/api/models/on-device/file").status_code == 401
        assert client.get("/health").status_code == 200

    def test_free_web_chat_still_skips_rag(self, client):
        with (
            patch("routers.chat._agents_reason", new_callable=AsyncMock) as reason,
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
        reason.assert_not_awaited()
        rag.assert_not_awaited()
        llm.assert_awaited()

    def test_file_download_is_rate_limited(self, client, tmp_path):
        settings = get_settings()
        settings.ONDEVICE_MODEL_DIR = str(tmp_path)
        settings.RATE_LIMIT_MODEL_FILE = 1
        _write_pack(tmp_path / "base", "qwen3.5-4b-base-q4", "free", b"base-weights")
        headers = auth_header(tier="free")
        assert client.get("/api/models/on-device/file", headers=headers).status_code == 200
        assert client.get("/api/models/on-device/file", headers=headers).status_code == 429

