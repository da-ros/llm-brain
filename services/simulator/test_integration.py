"""Router → Simulator with RAG and LLM mocked at the simulator boundary."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import ClassVar

import httpx
import jwt

os.environ.setdefault("SIMULATOR_STORE", "memory")
os.environ.setdefault("LLM_TEMPERATURE", "0")
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["KAFKA_ENABLED"] = "false"

SIM_ROOT = Path(__file__).resolve().parent
ROUTER_ROOT = SIM_ROOT.parent / "api-router"
SECRET = "test-secret-key-for-testing-only"

_SIM_MODULES = (
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
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class DispatchClient:
    """RAG GET and LLM POST are mocked. Router `request` enters the simulator app.

    Every service imports the same httpx module, so this one class has to
    tell the calls apart. The inner ASGI client is the real httpx class.
    """

    gets: ClassVar[list] = []
    posts: ClassVar[list] = []
    sim_app = None
    real_client = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None, headers=None):
        self.gets.append({"url": url, "params": params, "headers": headers})
        return FakeResponse(
            200,
            {
                "results": [
                    {
                        "document": "I slept 6 hours last night",
                        "metadata": {"source": "diary-1"},
                    }
                ],
                "total": 1,
            },
        )

    async def post(self, url, json=None, headers=None):
        self.posts.append({"url": url, "json": json, "headers": headers})
        content = (json or {}).get("messages", [{}])[0].get("content", "")
        leaf_ids: list[str] = []
        for line in content.splitlines():
            if line.startswith("LEAF_IDS: "):
                leaf_ids = [
                    part.strip() for part in line[len("LEAF_IDS: ") :].split(",") if part.strip()
                ]
        return FakeResponse(200, _llm_body(leaf_ids))

    async def request(self, method, url, json=None, params=None, headers=None):
        path = url.split("://", 1)[1]
        path = "/" + path.split("/", 1)[1]
        transport = httpx.ASGITransport(app=self.sim_app)
        async with self.real_client(transport=transport, base_url="http://simulator") as client:
            return await client.request(method, path, json=json, params=params, headers=headers)


def _token(user_id: str, tier: str = "premium") -> dict[str, str]:
    encoded = jwt.encode({"sub": user_id, "tier": tier}, SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {encoded}"}


def test_router_premium_simulate_reaches_simulator():
    """POST /api/simulate runs the simulator with mocked RAG and LLM. No Kafka."""
    import main as sim_main
    from fastapi.testclient import TestClient

    real_client = httpx.AsyncClient
    DispatchClient.gets = []
    DispatchClient.posts = []
    DispatchClient.sim_app = sim_main.app
    DispatchClient.real_client = real_client

    kept = {name: sys.modules.pop(name) for name in _SIM_MODULES if name in sys.modules}
    sys.path.insert(0, str(ROUTER_ROOT))
    snapshot = dict(sys.modules)
    httpx.AsyncClient = DispatchClient
    try:
        import auth
        import config as router_config
        import db as router_db
        import kafka_io as router_kafka
        import main as router_main
        import rate_limit as router_limit

        router_config.clear_settings_cache()
        router_limit.limiter.reset()

        async def _noop(*_args, **_kwargs):
            return None

        router_db.connect = _noop
        router_db.disconnect = _noop
        router_db.ensure_indexes = _noop
        kafka_calls = {"n": 0}

        def _no_kafka(*_args, **_kwargs):
            kafka_calls["n"] += 1

        router_kafka.publish_session_turn_completed = _no_kafka
        router_main.kafka_io.publish_session_turn_completed = _no_kafka

        with TestClient(router_main.app) as client:
            denied = client.post(
                "/api/simulate",
                headers=_token("user1", "free"),
                json={"question": "what if I change my sleep"},
            )
            assert denied.status_code == 403
            assert DispatchClient.posts == []

            created = client.post(
                "/api/simulate",
                headers=_token("user1"),
                json={"question": "what if I change my sleep"},
            )
            assert created.status_code == 200, created.text
            body = created.json()
            assert body["llm_used"] is True
            assert 3 <= body["scenario_count"] <= 5
            assert body["sources"] == ["diary-1"]
            assert any(
                scenario["trace"] == ["sleep_lt_7", "leaf:fatigue_high"]
                for scenario in body["scenarios"]
            )
            assert len(DispatchClient.posts) == 1
            assert DispatchClient.posts[0]["json"]["temperature"] == 0
            assert len(DispatchClient.gets) == 1
            assert kafka_calls["n"] == 0

            simulation_id = body["simulation_id"]
            own = client.get(f"/api/simulations/{simulation_id}", headers=_token("user1"))
            hidden = client.get(f"/api/simulations/{simulation_id}", headers=_token("user2"))
            listed = client.get("/api/simulations", headers=_token("user1"))
            other = client.get("/api/simulations", headers=_token("user2"))
            assert own.status_code == 200
            assert own.json()["scenarios"]
            assert hidden.status_code == 404
            assert any(
                row["simulation_id"] == simulation_id for row in listed.json()["simulations"]
            )
            assert all(row["simulation_id"] != simulation_id for row in other.json()["simulations"])

            for _ in range(9):
                extra = client.post(
                    "/api/simulate",
                    headers=_token("user1"),
                    json={"question": "what if I change my sleep"},
                )
                assert extra.status_code == 200
            blocked = client.post(
                "/api/simulate",
                headers=_token("user1"),
                json={"question": "what if I change my sleep"},
            )
            assert blocked.status_code == 429
            assert len(DispatchClient.posts) == 10
            assert kafka_calls["n"] == 0
            _ = auth
    finally:
        httpx.AsyncClient = real_client
        while str(ROUTER_ROOT) in sys.path:
            sys.path.remove(str(ROUTER_ROOT))
        for name in list(sys.modules):
            if name not in snapshot:
                del sys.modules[name]
        sys.modules.update(snapshot)
        sys.modules.update(kept)
        if str(SIM_ROOT) not in sys.path:
            sys.path.insert(0, str(SIM_ROOT))
