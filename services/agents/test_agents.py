"""Tests for Agents Service — LangGraph, MCP tools, isolation, Kafka learn_graph."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_response(status_code=200, json_data=None):
    """Create a mock HTTP response with proper attribute access."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    return resp

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
            "scan_message",
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

    def test_scan_message_forwards_to_shield(self, client):
        captured: dict = {}

        class FakeResponse:
            status_code = 200

            def json(self):
                return {
                    "alert": True,
                    "severity": "high",
                    "reasons": [{"type": "llm", "id": "llm"}],
                    "llm_used": True,
                }

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
                "/mcp/tools/scan_message",
                headers={"X-Request-ID": "cid-shield"},
                json={
                    "user_id": "user1",
                    "subscription_tier": "premium",
                    "source": "sms",
                    "text": "act now",
                },
            )
        assert response.status_code == 200
        assert captured["url"].endswith("/scan")
        assert captured["headers"]["X-Request-ID"] == "cid-shield"
        assert response.json()["alert"] is True
        assert response.json()["reasons"]

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

# ── Tools coverage (tools.py) ─────────────────────────────────────

class TestToolRegistry:
    def test_list_tools_returns_all_definitions(self):
        from tools import TOOL_DEFINITIONS, list_tools

        result = list_tools()
        assert len(result) == len(TOOL_DEFINITIONS)
        assert all("name" in t for t in result)

    @pytest.mark.asyncio
    async def test_invoke_tool_unknown_raises(self):
        from exceptions import UnknownToolError
        from tools import invoke_tool

        with pytest.raises(UnknownToolError):
            await invoke_tool("nonexistent_tool")

class TestRagSearch:
    @pytest.mark.asyncio
    async def test_rag_search_success(self):
        from tools import rag_search

        mock_resp = _mock_response(200, {
            "results": [
                {
                    "document": "chunk text",
                    "metadata": {"source": "doc1", "chunk_text": "chunk text"},
                }
            ]
        })
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.return_value = mock_resp
        with patch("tools.httpx.AsyncClient", return_value=mock_client):
            result = await rag_search(
                {"query": "test", "user_id": "u1", "correlation_id": "cid-1"}
            )
        assert "context" in result
        assert "sources" in result

    @pytest.mark.asyncio
    async def test_rag_search_http_error_returns_empty(self):
        from tools import rag_search

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.side_effect = __import__("httpx").HTTPError("connection refused")
        with patch("tools.httpx.AsyncClient", return_value=mock_client):
            result = await rag_search(
                {"query": "test", "user_id": "u1", "correlation_id": "cid-1"}
            )
        assert result["context"] == ""

    @pytest.mark.asyncio
    async def test_rag_search_non_200_returns_empty(self):
        from tools import rag_search

        mock_resp = _mock_response(503)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.return_value = mock_resp
        with patch("tools.httpx.AsyncClient", return_value=mock_client):
            result = await rag_search(
                {"query": "test", "user_id": "u1", "correlation_id": "cid-1"}
            )
        assert result["context"] == ""

class TestLlmGenerate:
    @pytest.mark.asyncio
    async def test_llm_generate_success(self):
        from tools import llm_generate

        mock_resp = _mock_response(200, {"response": "hello", "tokens_used": 10})
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch("tools.httpx.AsyncClient", return_value=mock_client):
            result = await llm_generate(
                {"query": "hi", "user_id": "u1", "correlation_id": "cid-1"}
            )
        assert result["response"] == "hello"

    @pytest.mark.asyncio
    async def test_llm_generate_timeout(self):
        from exceptions import LLMTimeoutError
        from tools import llm_generate

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=__import__("httpx").TimeoutException("t"))

        with patch("tools.httpx.AsyncClient", return_value=mock_client), pytest.raises(LLMTimeoutError):
                await llm_generate(
                    {"query": "hi", "user_id": "u1", "correlation_id": "c"}
                )

    @pytest.mark.asyncio
    async def test_llm_generate_500(self):
        from exceptions import LLMUpstreamError
        from tools import llm_generate

        mock_resp = _mock_response(500)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch("tools.httpx.AsyncClient", return_value=mock_client), pytest.raises(LLMUpstreamError):
                await llm_generate(
                    {"query": "hi", "user_id": "u1", "correlation_id": "c"}
                )

    @pytest.mark.asyncio
    async def test_llm_generate_504(self):
        from exceptions import LLMTimeoutError
        from tools import llm_generate

        mock_resp = _mock_response(504)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch("tools.httpx.AsyncClient", return_value=mock_client), pytest.raises(LLMTimeoutError):
                await llm_generate(
                    {"query": "hi", "user_id": "u1", "correlation_id": "c"}
                )

    @pytest.mark.asyncio
    async def test_llm_generate_400(self):
        from exceptions import LLMUpstreamError
        from tools import llm_generate

        mock_resp = _mock_response(400)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch("tools.httpx.AsyncClient", return_value=mock_client), pytest.raises(LLMUpstreamError):
                await llm_generate(
                    {"query": "hi", "user_id": "u1", "correlation_id": "c"}
                )

class TestIngestTurn:
    @pytest.mark.asyncio
    async def test_ingest_turn_stores(self):
        from tools import ingest_turn

        result = await ingest_turn(
            {
                "user_id": "u1",
                "session_id": "s1",
                "correlation_id": "cid-i1",
                "query": "q",
                "response": "r",
                "assumptions": ["a1"],
                "sources": ["s1"],
            }
        )
        assert "interaction" in result
        assert result["correlation_id"] == "cid-i1"

class TestEvaluateTurn:
    @pytest.mark.asyncio
    async def test_score_with_response(self):
        from tools import evaluate_turn

        result = await evaluate_turn(
            {
                "op": "score",
                "user_id": "u1",
                "correlation_id": "cid-e1",
                "session_id": "s1",
                "query": "q",
                "response": "good answer",
                "assumptions": ["a1"],
            }
        )
        assert result["score"] >= 0.5

    @pytest.mark.asyncio
    async def test_score_empty(self):
        from tools import evaluate_turn

        result = await evaluate_turn(
            {
                "op": "score",
                "user_id": "u1",
                "correlation_id": "cid-e2",
                "session_id": "s1",
                "query": "q",
                "response": "",
                "assumptions": [],
            }
        )
        assert result["score"] == 0.0

    @pytest.mark.asyncio
    async def test_append_batch(self):
        from tools import evaluate_turn

        result = await evaluate_turn(
            {
                "op": "append_batch",
                "user_id": "u1",
                "correlation_id": "cid-e3",
                "session_id": "s1",
                "query": "q",
                "response": "r",
                "assumptions": [],
            }
        )
        assert "batch" in result

class TestHeuristicScore:
    def test_full_score(self):
        from tools import heuristic_score

        score, _reason, _include = heuristic_score("answer", ["a1"])
        assert score == 1.0

    def test_empty_score(self):
        from tools import heuristic_score

        score, _reason, _include = heuristic_score("", [])
        assert score == 0.0

    def test_half_score(self):
        from tools import heuristic_score

        score, _reason, _include = heuristic_score("answer", [])
        assert score == 0.5

class TestFinetuneTrigger:
    @pytest.mark.asyncio
    async def test_success(self):
        from tools import finetune_trigger

        mock_resp = _mock_response(200, {"job_id": "j1", "status": "submitted"})
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch("tools.httpx.AsyncClient", return_value=mock_client):
            result = await finetune_trigger(
                {"user_id": "u1", "dataset_path": "/d.jsonl", "correlation_id": "c"}
            )
        assert result["job_id"] == "j1"

    @pytest.mark.asyncio
    async def test_http_error(self):
        from exceptions import LLMUpstreamError
        from tools import finetune_trigger

        mock_resp = _mock_response(500)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch("tools.httpx.AsyncClient", return_value=mock_client), pytest.raises(LLMUpstreamError):
                await finetune_trigger(
                    {"user_id": "u1", "dataset_path": "/d.jsonl", "correlation_id": "c"}
                )

    @pytest.mark.asyncio
    async def test_connection_error(self):
        from exceptions import LLMUpstreamError
        from tools import finetune_trigger

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=__import__("httpx").HTTPError("refused"))

        with patch("tools.httpx.AsyncClient", return_value=mock_client), pytest.raises(LLMUpstreamError):
                await finetune_trigger(
                    {"user_id": "u1", "dataset_path": "/d.jsonl", "correlation_id": "c"}
                )

class TestSimulateWhatif:
    @pytest.mark.asyncio
    async def test_success(self):
        from tools import simulate_whatif

        mock_resp = _mock_response(200, {"scenarios": []})
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch("tools.httpx.AsyncClient", return_value=mock_client):
            result = await simulate_whatif(
                {"user_id": "u1", "question": "what if", "correlation_id": "c"}
            )
        assert "scenarios" in result

    @pytest.mark.asyncio
    async def test_timeout(self):
        from exceptions import LLMTimeoutError
        from tools import simulate_whatif

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=__import__("httpx").TimeoutException("t"))

        with patch("tools.httpx.AsyncClient", return_value=mock_client), pytest.raises(LLMTimeoutError):
                await simulate_whatif(
                    {"user_id": "u1", "question": "what if", "correlation_id": "c"}
                )

    @pytest.mark.asyncio
    async def test_504(self):
        from exceptions import LLMTimeoutError
        from tools import simulate_whatif

        mock_resp = _mock_response(504)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch("tools.httpx.AsyncClient", return_value=mock_client), pytest.raises(LLMTimeoutError):
                await simulate_whatif(
                    {"user_id": "u1", "question": "what if", "correlation_id": "c"}
                )

    @pytest.mark.asyncio
    async def test_500(self):
        from exceptions import LLMUpstreamError
        from tools import simulate_whatif

        mock_resp = _mock_response(500)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch("tools.httpx.AsyncClient", return_value=mock_client), pytest.raises(LLMUpstreamError):
                await simulate_whatif(
                    {"user_id": "u1", "question": "what if", "correlation_id": "c"}
                )

    @pytest.mark.asyncio
    async def test_400(self):
        from fastapi import HTTPException
        from tools import simulate_whatif

        mock_resp = _mock_response(400, {"detail": "bad"})
        mock_resp.text = "bad"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch("tools.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(HTTPException) as exc:
                await simulate_whatif(
                    {"user_id": "u1", "question": "what if", "correlation_id": "c"}
                )
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_connection_error(self):
        from exceptions import LLMUpstreamError
        from tools import simulate_whatif

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=__import__("httpx").HTTPError("refused"))

        with patch("tools.httpx.AsyncClient", return_value=mock_client), pytest.raises(LLMUpstreamError):
                await simulate_whatif(
                    {"user_id": "u1", "question": "what if", "correlation_id": "c"}
                )

class TestScanMessage:
    @pytest.mark.asyncio
    async def test_success(self):
        from tools import scan_message

        mock_resp = _mock_response(200, {"alert": False, "severity": "low"})
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch("tools.httpx.AsyncClient", return_value=mock_client):
            result = await scan_message(
                {"user_id": "u1", "text": "hello", "correlation_id": "c"}
            )
        assert result["alert"] is False

    @pytest.mark.asyncio
    async def test_timeout(self):
        from exceptions import LLMTimeoutError
        from tools import scan_message

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=__import__("httpx").TimeoutException("t"))

        with patch("tools.httpx.AsyncClient", return_value=mock_client), pytest.raises(LLMTimeoutError):
                await scan_message(
                    {"user_id": "u1", "text": "hello", "correlation_id": "c"}
                )

    @pytest.mark.asyncio
    async def test_500(self):
        from exceptions import LLMUpstreamError
        from tools import scan_message

        mock_resp = _mock_response(500)
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch("tools.httpx.AsyncClient", return_value=mock_client), pytest.raises(LLMUpstreamError):
                await scan_message(
                    {"user_id": "u1", "text": "hello", "correlation_id": "c"}
                )

    @pytest.mark.asyncio
    async def test_400(self):
        from fastapi import HTTPException
        from tools import scan_message

        mock_resp = _mock_response(400, {"detail": "bad"})
        mock_resp.text = "bad"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post.return_value = mock_resp

        with patch("tools.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(HTTPException) as exc:
                await scan_message(
                    {"user_id": "u1", "text": "hello", "correlation_id": "c"}
                )
            assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_connection_error(self):
        from exceptions import LLMUpstreamError
        from tools import scan_message

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=__import__("httpx").HTTPError("refused"))

        with patch("tools.httpx.AsyncClient", return_value=mock_client), pytest.raises(LLMUpstreamError):
                await scan_message(
                    {"user_id": "u1", "text": "hello", "correlation_id": "c"}
                )

# ── DB coverage (db.py) ────────────────────────────────────────────

class TestDbMemory:
    def test_memory_store_init(self):
        from db import MemoryStore

        store = MemoryStore()
        assert store.interactions == {}

    def test_memory_store_reset(self):
        from db import MemoryStore

        store = MemoryStore()
        store.interactions["x"] = {"a": 1}
        store.reset()
        assert store.interactions == {}

    def test_iso_week(self):
        from db import _iso_week

        result = _iso_week()
        assert "W" in result

    def test_serialize_none(self):
        from db import _serialize

        assert _serialize(None) is None

    def test_serialize_with_id(self):
        from db import _serialize

        result = _serialize({"_id": 123, "name": "t"})
        assert result["_id"] == "123"

    def test_use_memory_true(self):
        from db import use_memory

        assert use_memory() is True

    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self):
        from db import connect, disconnect

        await connect()
        await disconnect()

    @pytest.mark.asyncio
    async def test_upsert_find_interaction(self):
        from db import find_interaction, upsert_interaction

        doc = {
            "user_id": "u1",
            "session_id": "s1",
            "correlation_id": "cid-d1",
            "query": "q",
            "response": "r",
        }
        await upsert_interaction(doc)
        found = await find_interaction("cid-d1")
        assert found is not None

    @pytest.mark.asyncio
    async def test_find_interaction_wrong_user(self):
        from db import find_interaction, upsert_interaction

        await upsert_interaction(
            {
                "user_id": "u1",
                "session_id": "s1",
                "correlation_id": "cid-d2",
                "query": "q",
                "response": "r",
            }
        )
        found = await find_interaction("cid-d2", user_id="wrong")
        assert found is None

    @pytest.mark.asyncio
    async def test_upsert_idempotent(self):
        from db import upsert_interaction

        doc = {
            "user_id": "u1",
            "session_id": "s1",
            "correlation_id": "cid-d3",
            "query": "q",
            "response": "r",
        }
        await upsert_interaction(doc)
        result = await upsert_interaction(doc)
        assert result["correlation_id"] == "cid-d3"

    @pytest.mark.asyncio
    async def test_find_interaction_not_found(self):
        from db import find_interaction

        assert await find_interaction("nonexistent") is None

    @pytest.mark.asyncio
    async def test_upsert_find_feedback(self):
        from db import find_feedback, upsert_feedback

        await upsert_feedback(
            {
                "user_id": "u1",
                "correlation_id": "cid-f1",
                "score": 0.8,
                "reason": "good",
                "should_include_in_batch": True,
            }
        )
        found = await find_feedback("cid-f1")
        assert found is not None
        assert found["score"] == 0.8

    @pytest.mark.asyncio
    async def test_find_feedback_wrong_user(self):
        from db import find_feedback, upsert_feedback

        await upsert_feedback(
            {
                "user_id": "u1",
                "correlation_id": "cid-f2",
                "score": 0.5,
                "reason": "ok",
                "should_include_in_batch": False,
            }
        )
        assert await find_feedback("cid-f2", user_id="wrong") is None

    @pytest.mark.asyncio
    async def test_find_feedback_not_found(self):
        from db import find_feedback

        assert await find_feedback("nonexistent") is None

    @pytest.mark.asyncio
    async def test_append_batch_creates(self):
        from db import append_batch_item

        batch = await append_batch_item(
            user_id="u1",
            item={"correlation_id": "cid-b1", "query": "q", "response": "r"},
        )
        assert batch["status"] == "ready"
        assert len(batch["items"]) == 1

    @pytest.mark.asyncio
    async def test_append_batch_no_duplicates(self):
        from db import append_batch_item

        item = {"correlation_id": "cid-b2", "query": "q", "response": "r"}
        await append_batch_item(user_id="u1", item=item)
        batch = await append_batch_item(user_id="u1", item=item)
        assert len(batch["items"]) == 1

    @pytest.mark.asyncio
    async def test_append_batch_submitted_unchanged(self):
        from db import _iso_week, append_batch_item, memory

        current_week = _iso_week()
        memory().batches["b-sub"] = {
            "_id": "b-sub",
            "user_id": "u1",
            "iso_week": current_week,
            "items": [{"correlation_id": "x"}],
            "status": "submitted",
        }
        batch = await append_batch_item(
            user_id="u1",
            item={"correlation_id": "new", "query": "q", "response": "r"},
        )
        assert batch["status"] == "submitted"

    @pytest.mark.asyncio
    async def test_find_batch(self):
        from db import append_batch_item, find_batch

        batch = await append_batch_item(
            user_id="u1",
            item={"correlation_id": "cid-b3", "query": "q", "response": "r"},
        )
        assert await find_batch(batch["_id"]) is not None

    @pytest.mark.asyncio
    async def test_find_batch_not_found(self):
        from db import find_batch

        assert await find_batch("nonexistent") is None

    @pytest.mark.asyncio
    async def test_list_batches(self):
        from db import append_batch_item, list_batches

        await append_batch_item(
            user_id="u-list",
            item={"correlation_id": "cid-l1", "query": "q", "response": "r"},
        )
        assert len(await list_batches("u-list")) >= 1

    @pytest.mark.asyncio
    async def test_list_batches_empty(self):
        from db import list_batches

        assert await list_batches("nobody") == []

    @pytest.mark.asyncio
    async def test_update_batch(self):
        from db import append_batch_item, update_batch

        batch = await append_batch_item(
            user_id="u1",
            item={"correlation_id": "cid-u1", "query": "q", "response": "r"},
        )
        updated = await update_batch(batch["_id"], {"status": "ready"})
        assert updated is not None
        assert updated["status"] == "ready"

    @pytest.mark.asyncio
    async def test_update_batch_not_found(self):
        from db import update_batch

        assert await update_batch("nope", {"status": "ready"}) is None

    @pytest.mark.asyncio
    async def test_append_batch_accumulating(self):
        from config import get_settings
        from db import append_batch_item

        original = get_settings().BATCH_MIN_ITEMS
        get_settings().BATCH_MIN_ITEMS = 5
        try:
            batch = await append_batch_item(
                user_id="u-acc",
                item={"correlation_id": "cid-acc", "query": "q", "response": "r"},
            )
            assert batch["status"] == "accumulating"
        finally:
            get_settings().BATCH_MIN_ITEMS = original

# ── Kafka IO coverage (kafka_io.py) ────────────────────────────────

class TestKafkaIo:
    @pytest.mark.asyncio
    async def test_process_missing_user_id(self):
        from kafka_io import process_session_turn

        result = await process_session_turn({"correlation_id": "c"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_process_with_user_id(self):
        from kafka_io import process_session_turn

        result = await process_session_turn(
            {
                "correlation_id": "c",
                "user_id": "u1",
                "session_id": "s1",
                "query": "q",
                "response": "r",
                "assumptions": [],
                "sources": [],
            }
        )
        assert isinstance(result, dict)

    def test_stop_consumer_thread(self):
        from kafka_io import stop_consumer_thread

        stop_consumer_thread()
