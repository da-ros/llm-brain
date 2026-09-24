"""Tests for Agents Service — LangGraph, MCP tools, isolation, Kafka learn_graph."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("KAFKA_ENABLED", "false")
os.environ.setdefault("AGENTS_STORE", "memory")
os.environ.setdefault("BATCH_MIN_ITEMS", "1")

_SERVICE_ROOT = Path(__file__).resolve().parent
_TOP_LEVEL = (
    "config",
    "main",
    "logging_setup",
    "exceptions",
    "base",
    "db",
    "tools",
    "state",
    "graphs",
    "razonador",
    "ingestor",
    "evaluador",
    "kafka_io",
)


def _isolate_service_imports() -> None:
    root_s = str(_SERVICE_ROOT)
    for name in list(sys.modules):
        if name not in _TOP_LEVEL and not any(name.startswith(f"{item}.") for item in _TOP_LEVEL):
            continue
        mod_file = getattr(sys.modules[name], "__file__", None) or ""
        if mod_file and Path(mod_file).resolve().is_relative_to(_SERVICE_ROOT):
            continue
        del sys.modules[name]
    if root_s in sys.path:
        sys.path.remove(root_s)
    sys.path.insert(0, root_s)


_isolate_service_imports()

from config import clear_settings_cache

clear_settings_cache()

from base import NO_PERSONAL_CONTEXT
from exceptions import LLMUpstreamError
from graphs import run_learn_graph, run_reason_graph
from kafka_io import process_session_turn
from main import app
from tools import HANDLERS, heuristic_score

UUID_LEN = 36


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _reason_state(**overrides):
    state = {
        "user_id": "user1",
        "session_id": "sess-1",
        "correlation_id": "cid-1",
        "query": "what medication do I take?",
        "context": "",
        "sources": [],
        "response": "",
        "assumptions": [],
        "tokens_used": 0,
        "error": None,
        "error_kind": None,
    }
    state.update(overrides)
    return state


def _learn_state(**overrides):
    state = {
        "user_id": "user1",
        "session_id": "sess-1",
        "correlation_id": "cid-learn",
        "query": "what medication do I take?",
        "response": "You take metformin.",
        "assumptions": [NO_PERSONAL_CONTEXT],
        "sources": [],
        "score": 0.0,
        "should_include_in_batch": False,
        "error": None,
    }
    state.update(overrides)
    return state


class TestHealth:
    def test_health_reports_langgraph(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["service"] == "agents-service"
        assert body["orchestrator"] == "langgraph"
        assert "secret" not in str(body).lower()

    def test_generates_correlation_id_when_missing(self, client):
        response = client.get("/health")
        correlation_id = response.headers.get("X-Request-ID")
        assert correlation_id
        assert len(correlation_id) == UUID_LEN

    def test_propagates_correlation_id(self, client):
        response = client.get("/health", headers={"X-Request-ID": "abc-123"})
        assert response.headers.get("X-Request-ID") == "abc-123"


class TestReasonGraph:
    """7.1 — reason_graph with mocked RAG/LLM."""

    @pytest.mark.asyncio
    async def test_context_hit(self):
        async def fake_rag(_arguments):
            return {"context": "Paciente toma metformina", "sources": ["receta.pdf"], "results": []}

        async def fake_llm(_arguments):
            return {"response": "Tomas metformina.", "tokens_used": 11}

        with (
            patch.dict(HANDLERS, {"rag_search": fake_rag, "llm_generate": fake_llm}),
        ):
            result = await run_reason_graph(_reason_state())
        assert result["response"] == "Tomas metformina."
        assert result["sources"] == ["receta.pdf"]
        assert result["tokens_used"] == 11
        assert result["assumptions"]
        assert NO_PERSONAL_CONTEXT not in result["assumptions"]
        assert not result.get("error")

    @pytest.mark.asyncio
    async def test_empty_rag_includes_no_personal_context(self):
        async def fake_rag(_arguments):
            return {"context": "", "sources": [], "results": []}

        async def fake_llm(_arguments):
            return {"response": "I do not have personal records for that.", "tokens_used": 8}

        with patch.dict(HANDLERS, {"rag_search": fake_rag, "llm_generate": fake_llm}):
            result = await run_reason_graph(_reason_state())
        assert result["response"]
        assert result["sources"] == []
        assert NO_PERSONAL_CONTEXT in result["assumptions"]

    @pytest.mark.asyncio
    async def test_llm_5xx_error_end_skips_assumptions(self):
        async def fake_rag(_arguments):
            return {"context": "notes", "sources": ["doc-1"], "results": []}

        async def fake_llm(_arguments):
            raise LLMUpstreamError("LLM service HTTP 500")

        with patch.dict(HANDLERS, {"rag_search": fake_rag, "llm_generate": fake_llm}):
            result = await run_reason_graph(_reason_state())
        assert result.get("error")
        assert result.get("error_kind") == "upstream"
        assert not result.get("assumptions")


class TestLearnGraph:
    """7.2 — ingest idempotency; Evaluador never auto-trains."""

    @pytest.mark.asyncio
    async def test_ingest_is_idempotent_on_correlation_id(self):
        import db

        train = AsyncMock(side_effect=AssertionError("Evaluador must not call Fine-Tune"))
        with patch.dict(HANDLERS, {"finetune_trigger": train}):
            await run_learn_graph(_learn_state(correlation_id="dup-1"))
            await run_learn_graph(_learn_state(correlation_id="dup-1"))
        train.assert_not_called()
        assert len(db.memory().interactions) == 1
        assert "dup-1" in db.memory().interactions

    @pytest.mark.asyncio
    async def test_evaluador_does_not_auto_train(self):
        train = AsyncMock()
        with patch.dict(HANDLERS, {"finetune_trigger": train}):
            result = await run_learn_graph(_learn_state(correlation_id="no-train"))
        train.assert_not_called()
        assert result["should_include_in_batch"] is True
        import db

        feedback = db.memory().feedback["no-train"]
        assert feedback["score"] >= 0.6
        assert feedback["should_include_in_batch"] is True
        batches = list(db.memory().batches.values())
        assert batches
        assert batches[0]["status"] in {"accumulating", "ready"}

    def test_heuristic_requires_answer_and_assumptions(self):
        score, _reason, include = heuristic_score("an answer", ["assumption"])
        assert score == 1.0
        assert include is True
        score, _reason, include = heuristic_score("an answer", [])
        assert include is False


class TestIsolationAndMcp:
    """7.3 — Free 403, cross-user 404, unknown MCP tool 404."""

    def test_free_reason_forbidden(self, client):
        response = client.post(
            "/reason",
            json={
                "user_id": "user1",
                "subscription_tier": "free",
                "message": "hello",
            },
        )
        assert response.status_code == 403

    def test_unknown_mcp_tool_404(self, client):
        response = client.post("/mcp/tools/not_a_tool", json={"user_id": "user1"})
        assert response.status_code == 404

    def test_mcp_lists_required_tools(self, client):
        response = client.get("/mcp/tools")
        assert response.status_code == 200
        names = {tool["name"] for tool in response.json()["tools"]}
        assert names >= {
            "rag_search",
            "llm_generate",
            "ingest_turn",
            "evaluate_turn",
            "finetune_trigger",
            "simulate_whatif",
        }

    def test_simulate_whatif_forwards_to_simulator(self, client):
        captured: dict = {}

        class FakeResponse:
            status_code = 200

            def json(self):
                return {"llm_used": True, "scenario_count": 3, "scenarios": []}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url, json=None, headers=None):
                captured["url"] = url
                captured["json"] = json
                captured["headers"] = headers
                return FakeResponse()

        with patch("tools.httpx.AsyncClient", FakeClient):
            response = client.post(
                "/mcp/tools/simulate_whatif",
                headers={"X-Request-ID": "cid-sim"},
                json={
                    "user_id": "user1",
                    "subscription_tier": "premium",
                    "question": "what if I sleep less",
                },
            )
        assert response.status_code == 200
        assert captured["url"].endswith("/simulate")
        assert captured["headers"]["X-Request-ID"] == "cid-sim"
        assert captured["json"]["question"] == "what if I sleep less"
        assert response.json()["llm_used"] is True

    def test_simulate_whatif_upstream_is_502(self, client):
        class FakeResponse:
            status_code = 500
            text = "down"

            def json(self):
                return {"detail": "down"}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url, json=None, headers=None):
                return FakeResponse()

        with patch("tools.httpx.AsyncClient", FakeClient):
            response = client.post(
                "/mcp/tools/simulate_whatif",
                json={
                    "user_id": "user1",
                    "subscription_tier": "premium",
                    "question": "what if I sleep less",
                },
            )
        assert response.status_code == 502
        assert "scenarios" not in response.json()

    def test_unknown_mcp_tool_still_404(self, client):
        response = client.post("/mcp/tools/not_a_tool", json={"user_id": "user1"})
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_user_batch_is_404(self, client):
        import db

        await db.append_batch_item(
            user_id="owner",
            item={
                "correlation_id": "cid-owner",
                "query": "q",
                "response": "a",
                "assumptions": ["x"],
            },
        )
        batch_id = next(iter(db.memory().batches))
        response = client.get(f"/batches/{batch_id}", params={"user_id": "intruder"})
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_user_interaction_is_404(self, client):
        import db

        await db.upsert_interaction(
            {
                "user_id": "owner",
                "session_id": "s1",
                "correlation_id": "cid-owner",
                "query": "q",
                "response": "a",
                "assumptions": [],
                "sources": [],
            }
        )
        response = client.get("/interactions/cid-owner", params={"user_id": "intruder"})
        assert response.status_code == 404

    def test_free_mcp_tool_forbidden(self, client):
        response = client.post(
            "/mcp/tools/rag_search",
            json={"user_id": "user1", "subscription_tier": "free", "query": "hi"},
        )
        assert response.status_code == 403


class TestReasonEndpoint:
    def test_reason_maps_llm_5xx_to_502(self, client):
        async def fake_rag(_arguments):
            return {"context": "", "sources": [], "results": []}

        async def fake_llm(_arguments):
            raise LLMUpstreamError("LLM service HTTP 500")

        with patch.dict(HANDLERS, {"rag_search": fake_rag, "llm_generate": fake_llm}):
            response = client.post(
                "/reason",
                json={
                    "user_id": "user1",
                    "subscription_tier": "premium",
                    "message": "hello",
                },
                headers={"X-Request-ID": "cid-502"},
            )
        assert response.status_code == 502
        assert response.headers.get("X-Request-ID") == "cid-502"

    def test_reason_success_returns_assumptions(self, client):
        async def fake_rag(_arguments):
            return {"context": "notes", "sources": ["doc-1"], "results": []}

        async def fake_llm(_arguments):
            return {"response": "Based on your notes, yes.", "tokens_used": 4}

        with patch.dict(HANDLERS, {"rag_search": fake_rag, "llm_generate": fake_llm}):
            response = client.post(
                "/reason",
                json={
                    "user_id": "user1",
                    "subscription_tier": "premium",
                    "message": "hello",
                    "session_id": "sess-9",
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["response"]
        assert body["assumptions"]
        assert body["session_id"] == "sess-9"
        assert body["sources"] == ["doc-1"]


class TestLearnAndTrigger:
    """7.4 — Kafka learn_graph + manual trigger with mocked Fine-Tune."""

    @pytest.mark.asyncio
    async def test_kafka_message_runs_learn_graph(self):
        train = AsyncMock()
        with patch.dict(HANDLERS, {"finetune_trigger": train}):
            result = await process_session_turn(
                {
                    "correlation_id": "k-1",
                    "user_id": "user1",
                    "session_id": "sess-k",
                    "query": "q",
                    "response": "a",
                    "assumptions": ["assumption"],
                    "sources": [],
                }
            )
        train.assert_not_called()
        assert result["should_include_in_batch"] is True
        import db

        assert "k-1" in db.memory().interactions

    @pytest.mark.asyncio
    async def test_manual_trigger_calls_finetune(self, client, tmp_path, monkeypatch):
        import db
        from config import clear_settings_cache

        monkeypatch.setenv("BATCH_EXPORT_DIR", str(tmp_path))
        clear_settings_cache()
        batch = await db.append_batch_item(
            user_id="user1",
            item={
                "correlation_id": "ready-1",
                "query": "q",
                "response": "a",
                "assumptions": ["x"],
            },
        )
        assert batch["status"] == "ready"
        batch_id = batch["_id"]

        async def fake_train(_arguments):
            return {"job_id": "ft-job-1", "status": "submitted"}

        with patch.dict(HANDLERS, {"finetune_trigger": fake_train}):
            response = client.post(
                f"/batches/{batch_id}/trigger",
                json={"user_id": "user1", "subscription_tier": "premium"},
            )
        assert response.status_code == 202
        body = response.json()
        assert body["job_id"] == "ft-job-1"
        assert body["status"] == "submitted"
        stored = db.memory().batches[batch_id]
        assert stored["status"] == "submitted"
        assert stored["job_id"] == "ft-job-1"
        assert stored["dataset_path"]
        assert stored["dataset_path"].endswith(".jsonl")

    @pytest.mark.asyncio
    async def test_trigger_not_ready_is_409(self, client):
        import db
        from config import get_settings

        original = get_settings().BATCH_MIN_ITEMS
        get_settings().BATCH_MIN_ITEMS = 10
        try:
            # Force accumulating by writing directly after a 1-item append with min=10
            db.memory().batches["b-empty"] = {
                "_id": "b-empty",
                "user_id": "user1",
                "iso_week": "2026-W38",
                "items": [],
                "status": "accumulating",
            }
            response = client.post(
                "/batches/b-empty/trigger",
                json={"user_id": "user1", "subscription_tier": "premium"},
            )
        finally:
            get_settings().BATCH_MIN_ITEMS = original
        assert response.status_code == 409

    def test_trigger_other_users_batch_404(self, client):
        import db

        db.memory().batches["b-owner"] = {
            "_id": "b-owner",
            "user_id": "owner",
            "iso_week": "2026-W38",
            "items": [{"correlation_id": "x", "query": "q", "response": "a"}],
            "status": "ready",
        }
        response = client.post(
            "/batches/b-owner/trigger",
            json={"user_id": "intruder", "subscription_tier": "premium"},
        )
        assert response.status_code == 404
