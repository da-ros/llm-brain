"""Tests for the Decision-Support Simulator."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SIMULATOR_STORE", "memory")
os.environ.setdefault("LLM_TEMPERATURE", "0")

_SERVICE_ROOT = Path(__file__).resolve().parent
_TOP_LEVEL = (
    "config",
    "main",
    "logging_setup",
    "exceptions",
    "base",
    "db",
    "engine",
    "rag_client",
    "llm_client",
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

import db
from engine import detect_families, walk_tree
from exceptions import InvalidScenarioJSONError
from llm_client import SCENARIO_MAX_NEW_TOKENS, parse_scenarios
from main import app

UUID_LEN = 36


def _llm_body(leaf_ids: list[str]) -> dict:
    return {
        "response": json.dumps(
            {
                "scenarios": [
                    {
                        "id": leaf_id,
                        "title": f"Title {leaf_id}",
                        "outcome": f"Outcome {leaf_id}",
                        "assumptions": [f"Assumption for {leaf_id}"],
                    }
                    for leaf_id in leaf_ids
                ]
            }
        ),
        "tokens_used": 4,
    }


class FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = payload if isinstance(payload, str) else json.dumps(payload)

    def json(self):
        if isinstance(self._payload, str):
            return json.loads(self._payload)
        return self._payload


class RecordingClient:
    """Stand-in for httpx.AsyncClient. Class-level call log."""

    gets: ClassVar[list] = []
    posts: ClassVar[list] = []
    rag_status: int = 200
    rag_results: list[dict] | None = None
    llm_status: int = 200
    llm_payloads: list | None = None
    raise_timeout_on: str | None = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None, headers=None):
        if self.raise_timeout_on == "rag":
            import httpx

            raise httpx.TimeoutException("rag timeout")
        self.gets.append({"url": url, "params": params, "headers": headers})
        results = [] if self.rag_results is None else self.rag_results
        return FakeResponse(self.rag_status, {"results": results, "total": len(results)})

    async def post(self, url, json=None, headers=None):
        if self.raise_timeout_on == "llm":
            import httpx

            raise httpx.TimeoutException("llm timeout")
        self.posts.append({"url": url, "json": json, "headers": headers})
        if self.llm_payloads is not None:
            payload = self.llm_payloads.pop(0)
            return FakeResponse(self.llm_status, payload)
        content = (json or {}).get("messages", [{}])[0].get("content", "")
        marker = "LEAF_IDS: "
        leaf_ids = []
        for line in content.splitlines():
            if line.startswith(marker):
                leaf_ids = [part.strip() for part in line[len(marker) :].split(",") if part.strip()]
        return FakeResponse(self.llm_status, _llm_body(leaf_ids))


def _reset_bound_store() -> None:
    """Clear the store the live app writes to, not a re-imported db module."""
    db.reset_memory()
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        globals_ = getattr(endpoint, "__globals__", None)
        if globals_ and "db" in globals_:
            globals_["db"].reset_memory()
            return


@pytest.fixture
def client():
    RecordingClient.gets = []
    RecordingClient.posts = []
    RecordingClient.rag_status = 200
    RecordingClient.rag_results = None
    RecordingClient.llm_status = 200
    RecordingClient.llm_payloads = None
    RecordingClient.raise_timeout_on = None
    _reset_bound_store()
    with (
        pytest.MonkeyPatch.context() as patcher,
        TestClient(app) as test_client,
    ):
        patcher.setattr("rag_client.httpx.AsyncClient", RecordingClient)
        patcher.setattr("llm_client.httpx.AsyncClient", RecordingClient)
        yield test_client
    _reset_bound_store()


def _premium(question: str, variables: dict | None = None, **headers):
    payload = {
        "user_id": "user1",
        "subscription_tier": "premium",
        "question": question,
    }
    if variables is not None:
        payload["variables"] = variables
    return payload


class TestHealth:
    def test_health_is_public(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["service"] == "simulator-service"
        assert "secret" not in str(body).lower()

    def test_generates_correlation_id_when_missing(self, client):
        response = client.get("/health")
        correlation_id = response.headers.get("X-Request-ID")
        assert correlation_id
        assert len(correlation_id) == UUID_LEN


class TestTree:
    def test_single_family_is_three_leaves(self):
        families = detect_families("what if I sleep less", {"sleep_hours": 5})
        leaves = walk_tree(families, {"sleep_hours": 5})
        assert [leaf["id"] for leaf in leaves] == ["optimistic", "baseline", "pessimistic"]
        assert leaves[2]["trace"] == ["sleep_lt_7", "leaf:fatigue_high"]

    def test_many_families_cap_at_five(self):
        question = "what if my sleep, meetings, budget, and prescriptions all change"
        families = detect_families(question, None)
        assert families == ["sleep", "time", "money", "health"]
        variables = {
            "sleep_hours": 8,
            "meeting_hours_per_day": 3,
            "focus_hours_per_day": 4,
            "monthly_spend": 0,
            "active_prescriptions": 0,
        }
        leaves = walk_tree(families, variables)
        assert 3 <= len(leaves) <= 5
        assert len(leaves) == 5
        assert [leaf["id"] for leaf in leaves[:3]] == ["optimistic", "baseline", "pessimistic"]

    def test_same_inputs_same_traces(self):
        variables = {
            "sleep_hours": 6,
            "meeting_hours_per_day": 5,
            "focus_hours_per_day": 2,
        }
        question = "what if I sleep less and add meetings"
        first = walk_tree(detect_families(question, variables), variables)
        second = walk_tree(detect_families(question, variables), variables)
        assert [leaf["trace"] for leaf in first] == [leaf["trace"] for leaf in second]
        assert len(first) == 4


class TestSimulate:
    def test_success_calls_llm_once_and_sets_llm_used(self, client):
        response = client.post(
            "/simulate",
            headers={"X-Request-ID": "cid-1"},
            json=_premium("what if I sleep less", {"sleep_hours": 5}),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["llm_used"] is True
        assert 3 <= body["scenario_count"] <= 5
        assert len(RecordingClient.posts) == 1
        assert RecordingClient.posts[0]["json"]["temperature"] == 0
        assert RecordingClient.posts[0]["json"]["max_new_tokens"] == SCENARIO_MAX_NEW_TOKENS
        assert RecordingClient.posts[0]["headers"]["X-Request-ID"] == "cid-1"
        assert RecordingClient.gets == []
        for scenario in body["scenarios"]:
            assert scenario["title"]
            assert scenario["outcome"]
            assert scenario["assumptions"]
            assert scenario["trace"]
        traces = [scenario["trace"] for scenario in body["scenarios"]]
        assert ["sleep_lt_7", "leaf:fatigue_high"] in traces
        stored = db.memory().by_correlation["cid-1"]
        assert stored["user_id"] == "user1"

    def test_same_inputs_same_leaf_traces(self, client):
        payload = _premium("what if I sleep less", {"sleep_hours": 5})
        first = client.post("/simulate", headers={"X-Request-ID": "cid-a"}, json=payload)
        second = client.post("/simulate", headers={"X-Request-ID": "cid-b"}, json=payload)
        assert first.status_code == 200
        assert second.status_code == 200
        assert [item["trace"] for item in first.json()["scenarios"]] == [
            item["trace"] for item in second.json()["scenarios"]
        ]
        assert len(RecordingClient.posts) == 2

    def test_llm_5xx_does_not_persist(self, client):
        RecordingClient.llm_status = 500
        response = client.post(
            "/simulate",
            headers={"X-Request-ID": "cid-fail"},
            json=_premium("what if I sleep less", {"sleep_hours": 5}),
        )
        assert response.status_code == 502
        assert "cid-fail" not in db.memory().by_correlation
        assert db.memory().by_id == {}

    def test_llm_timeout_is_504(self, client):
        RecordingClient.raise_timeout_on = "llm"
        response = client.post(
            "/simulate",
            headers={"X-Request-ID": "cid-timeout"},
            json=_premium("what if I sleep less", {"sleep_hours": 5}),
        )
        assert response.status_code == 504
        assert db.memory().by_id == {}

    def test_invalid_json_retries_once_then_502(self, client):
        RecordingClient.llm_payloads = [
            {"response": "not-json", "tokens_used": 1},
            {"response": "still-not-json", "tokens_used": 1},
        ]
        response = client.post(
            "/simulate",
            headers={"X-Request-ID": "cid-json"},
            json=_premium("what if I sleep less", {"sleep_hours": 5}),
        )
        assert response.status_code == 502
        assert len(RecordingClient.posts) == 2
        assert db.memory().by_id == {}

    def test_partial_batch_fetches_the_missing_leaves(self, client):
        def row(leaf_id: str) -> dict:
            return {
                "id": leaf_id,
                "title": f"Title {leaf_id}",
                "outcome": f"Outcome {leaf_id}",
                "assumptions": [f"Assumption for {leaf_id}"],
            }

        RecordingClient.llm_payloads = [
            {"response": json.dumps({"scenarios": [row("optimistic")]}), "tokens_used": 1},
            {"response": json.dumps(row("baseline")), "tokens_used": 1},
            {"response": json.dumps(row("pessimistic")), "tokens_used": 1},
        ]
        response = client.post(
            "/simulate",
            headers={"X-Request-ID": "cid-partial"},
            json=_premium("what if I sleep less", {"sleep_hours": 5}),
        )
        assert response.status_code == 200
        assert len(RecordingClient.posts) == 3
        titles = [scenario["title"] for scenario in response.json()["scenarios"]]
        assert titles == ["Title optimistic", "Title baseline", "Title pessimistic"]


class TestHydration:
    def test_rag_hit_parses_sleep(self, client):
        RecordingClient.rag_results = [
            {"document": "I slept 6 hours last night", "metadata": {"source": "diary-1"}}
        ]
        response = client.post(
            "/simulate",
            headers={"X-Request-ID": "cid-rag"},
            json=_premium("what if I change my sleep"),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["sources"] == ["diary-1"]
        assert len(RecordingClient.gets) == 1
        assert RecordingClient.gets[0]["params"]["user_id"] == "user1"
        assert RecordingClient.gets[0]["headers"]["X-Request-ID"] == "cid-rag"
        traces = [scenario["trace"] for scenario in body["scenarios"]]
        assert ["sleep_lt_7", "leaf:fatigue_high"] in traces

    def test_rag_empty_uses_default_assumption(self, client):
        RecordingClient.rag_results = []
        response = client.post(
            "/simulate",
            headers={"X-Request-ID": "cid-empty"},
            json=_premium("what if I change my sleep"),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["sources"] == []
        assert 3 <= body["scenario_count"] <= 5
        joined = " ".join(body["assumptions"])
        assert "No personal context was found for sleep_hours" in joined
        assert "used default 7h" in joined

    def test_rag_5xx_does_not_persist(self, client):
        RecordingClient.rag_status = 500
        response = client.post(
            "/simulate",
            headers={"X-Request-ID": "cid-rag-down"},
            json=_premium("what if I change my sleep"),
        )
        assert response.status_code == 502
        assert db.memory().by_id == {}
        assert RecordingClient.posts == []

    def test_rag_timeout_is_504(self, client):
        RecordingClient.raise_timeout_on = "rag"
        response = client.post(
            "/simulate",
            headers={"X-Request-ID": "cid-rag-timeout"},
            json=_premium("what if I change my sleep"),
        )
        assert response.status_code == 504
        assert db.memory().by_id == {}

    def test_idempotent_correlation_skips_llm(self, client):
        payload = _premium("what if I sleep less", {"sleep_hours": 5})
        headers = {"X-Request-ID": "cid-same"}
        first = client.post("/simulate", headers=headers, json=payload)
        second = client.post("/simulate", headers=headers, json=payload)
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["simulation_id"] == second.json()["simulation_id"]
        assert len(RecordingClient.posts) == 1
        assert len(db.memory().by_id) == 1

    def test_blank_question_is_422(self, client):
        response = client.post(
            "/simulate",
            json=_premium("   "),
        )
        assert response.status_code == 422
        assert RecordingClient.posts == []
        assert db.memory().by_id == {}


class TestIsolation:
    def test_free_tier_is_403(self, client):
        response = client.post(
            "/simulate",
            json={
                "user_id": "user1",
                "subscription_tier": "free",
                "question": "what if I sleep less",
            },
        )
        assert response.status_code == 403
        assert RecordingClient.posts == []
        assert db.memory().by_id == {}

    def test_cross_user_get_is_404(self, client):
        created = client.post(
            "/simulate",
            headers={"X-Request-ID": "cid-owner"},
            json=_premium("what if I sleep less", {"sleep_hours": 8}),
        )
        simulation_id = created.json()["simulation_id"]
        hidden = client.get(
            f"/simulations/{simulation_id}",
            params={"user_id": "intruder", "subscription_tier": "premium"},
        )
        assert hidden.status_code == 404
        own = client.get(
            f"/simulations/{simulation_id}",
            params={"user_id": "user1", "subscription_tier": "premium"},
        )
        assert own.status_code == 200
        assert own.json()["scenarios"][0]["trace"]

    def test_list_filters_by_user(self, client):
        client.post(
            "/simulate",
            headers={"X-Request-ID": "cid-u1"},
            json=_premium("what if I sleep less", {"sleep_hours": 8}),
        )
        other = _premium("what if I sleep less", {"sleep_hours": 8})
        other["user_id"] = "user2"
        client.post("/simulate", headers={"X-Request-ID": "cid-u2"}, json=other)
        listed = client.get(
            "/simulations",
            params={"user_id": "user1", "subscription_tier": "premium"},
        )
        assert listed.status_code == 200
        rows = listed.json()["simulations"]
        assert len(rows) == 1
        assert rows[0]["correlation_id"] == "cid-u1"
        assert rows[0]["question"] == "what if I sleep less"
        assert rows[0]["created_at"]


_LEAVES = [
    {"id": "optimistic", "leaf_id": "leaf:rested", "trace": ["sleep_gte_7", "leaf:rested"]},
    {
        "id": "baseline",
        "leaf_id": "leaf:sleep_baseline",
        "trace": ["sleep_eq_current", "leaf:sleep_baseline"],
    },
    {
        "id": "pessimistic",
        "leaf_id": "leaf:fatigue_risk",
        "trace": ["sleep_drop", "leaf:fatigue_risk"],
    },
]


def _authored(ids: list[str], *, assumptions: object = None) -> str:
    rows = []
    for leaf_id in ids:
        rows.append(
            {
                "id": leaf_id,
                "title": f"Title {leaf_id}",
                "outcome": f"Outcome {leaf_id}",
                "assumptions": assumptions
                if assumptions is not None
                else [f"Assumption for {leaf_id}"],
            }
        )
    return json.dumps({"scenarios": rows})


class TestParseScenarios:
    def test_leaf_name_is_accepted_as_the_scenario_id(self):
        text = _authored(["leaf:rested", "leaf:sleep_baseline", "leaf:fatigue_risk"])
        parsed = parse_scenarios(text, _LEAVES)
        assert [row["id"] for row in parsed] == ["optimistic", "baseline", "pessimistic"]

    def test_assumption_string_becomes_a_list(self):
        text = _authored(
            ["optimistic", "baseline", "pessimistic"],
            assumptions="Sleep stays at the default.",
        )
        parsed = parse_scenarios(text, _LEAVES)
        assert parsed[0]["assumptions"] == ["Sleep stays at the default."]

    def test_thinking_fence_and_trailing_comma_still_parse(self):
        body = _authored(["optimistic", "baseline", "pessimistic"]).rstrip("}") + ",}"
        text = f"<think>draft</think>\n```json\n{body}\n```"
        parsed = parse_scenarios(text, _LEAVES)
        assert parsed[1]["title"] == "Title baseline"

    def test_prose_without_json_is_rejected(self):
        with pytest.raises(InvalidScenarioJSONError):
            parse_scenarios("I would work half time and go to the gym.", _LEAVES)
