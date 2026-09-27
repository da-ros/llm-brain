"""Tests for the Privacy & Scam Shield."""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SHIELD_STORE", "memory")
os.environ.setdefault("LLM_TEMPERATURE", "0")

_SERVICE_ROOT = Path(__file__).resolve().parent
_TOP_LEVEL = (
    "config",
    "main",
    "logging_setup",
    "exceptions",
    "base",
    "db",
    "heuristics",
    "ocr",
    "corpus",
    "rag_client",
    "llm_client",
    "scan",
    "guidelines",
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
from main import app

_EVENTS: list[str] = []
_CHAT: list = []


def _verdict(alert: bool, severity: str = "high") -> dict:
    return {
        "response": json.dumps(
            {
                "likelihood": 0.91 if alert else 0.05,
                "alert": alert,
                "severity": severity if alert else "none",
                "summary": "Likely scam" if alert else "Looks ordinary",
                "rationale": "Model rationale",
            }
        ),
        "tokens_used": 3,
    }


class FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = payload if isinstance(payload, str) else json.dumps(payload)

    def json(self):
        if isinstance(self._payload, str):
            return {"response": self._payload}
        return self._payload


class FakeClient:
    chat_calls = 0
    embed_status = 200
    bad_json_once = False
    _bad_used = False

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        if url.endswith("/embed"):
            if FakeClient.embed_status >= 500:
                return FakeResponse(FakeClient.embed_status, {"detail": "down"})
            vector = [0.0] * 2048
            text = (json or {}).get("text") or (json or {}).get("modality") or ""
            vector[abs(hash(text)) % 2048] = 1.0
            return FakeResponse(200, {"vector": vector, "modality": (json or {}).get("modality")})
        FakeClient.chat_calls += 1
        _CHAT.append(json)
        if FakeClient.bad_json_once and not FakeClient._bad_used:
            FakeClient._bad_used = True
            return FakeResponse(200, {"response": "not-json", "tokens_used": 1})
        alert = "won" in str(json).lower() or "act now" in str(json).lower()
        return FakeResponse(200, _verdict(alert))


def _reset_fake():
    FakeClient.chat_calls = 0
    FakeClient.embed_status = 200
    FakeClient.bad_json_once = False
    FakeClient._bad_used = False
    _EVENTS.clear()
    _CHAT.clear()


def _ocr(payload: bytes, suffix: str = ".png") -> str:
    _EVENTS.append("ocr")
    return "Act now and verify password"


@pytest.fixture
def client(monkeypatch):
    _reset_fake()
    monkeypatch.setattr("rag_client.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr("llm_client.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr("ocr.ocr_image", _ocr)
    monkeypatch.setattr("scan.ocr_image", _ocr)

    def _heuristics(text: str):
        _EVENTS.append("heuristics")
        from heuristics import run_heuristics

        return run_heuristics(text)

    monkeypatch.setattr("scan.run_heuristics", _heuristics)
    db.reset_memory()
    import scan

    scan.reset_gallery()
    with TestClient(app) as test_client:
        yield test_client
    db.reset_memory()
    scan.reset_gallery()


def _scan(client, **overrides):
    body = {
        "user_id": "user1",
        "subscription_tier": "premium",
        "source": "email",
        "text": "Act now and verify password",
    }
    body.update(overrides)
    return client.post("/scan", headers={"X-Request-ID": body.pop("cid", "cid-1")}, json=body)


class TestScan:
    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == "shield-service"

    def test_text_scan_calls_llm_once_and_follows_alert(self, client):
        response = _scan(client)
        assert response.status_code == 200
        body = response.json()
        assert body["llm_used"] is True
        assert body["alert"] is True
        assert FakeClient.chat_calls == 1
        types = {item["type"] for item in body["reasons"]}
        assert "heuristic" in types
        assert "llm" in types
        assert "embedding" in types
        assert db.memory().by_id

    def test_image_ocr_before_heuristics(self, client):
        raw = base64.b64encode(b"png-bytes").decode()
        response = _scan(
            client,
            source="image",
            text="",
            content_base64=raw,
            filename="shot.png",
            cid="cid-img",
        )
        assert response.status_code == 200
        assert _EVENTS[0] == "ocr"
        assert "heuristics" in _EVENTS
        assert _EVENTS.index("ocr") < _EVENTS.index("heuristics")
        assert response.json()["llm_used"] is True
        assert any(item["id"] == "ocr_text" for item in response.json()["reasons"])
        assert FakeClient.chat_calls == 1
        content = _CHAT[0]["messages"][0]["content"]
        assert isinstance(content, list)

    def test_video_does_not_ocr(self, client):
        raw = base64.b64encode(b"mp4-bytes").decode()
        response = _scan(
            client,
            source="video",
            text="hello from a clip",
            content_base64=raw,
            filename="clip.mp4",
            cid="cid-vid",
        )
        assert response.status_code == 200
        assert "ocr" not in _EVENTS
        assert response.json()["llm_used"] is True
        assert isinstance(response.json()["likelihood"], float)
        assert FakeClient.chat_calls == 1

    def test_ham_alert_false_does_not_persist(self, client):
        response = _scan(client, text="Dinner at 7 at the usual place.", cid="cid-ham")
        assert response.status_code == 200
        assert response.json()["alert"] is False
        assert any(item["type"] == "llm" for item in response.json()["reasons"])
        assert db.memory().by_id == {}

    def test_missing_content_is_422(self, client):
        before = FakeClient.chat_calls
        response = _scan(client, text="", content_base64="", cid="cid-empty")
        assert response.status_code == 422
        assert FakeClient.chat_calls == before
        assert db.memory().by_id == {}

    def test_embed_failure_still_calls_llm(self, client):
        FakeClient.embed_status = 500
        import scan

        scan.reset_gallery()
        response = _scan(client, cid="cid-embed")
        assert response.status_code == 200
        assert FakeClient.chat_calls == 1
        assert any(item["id"] == "embedding_unavailable" for item in response.json()["reasons"])

    def test_llm_5xx_does_not_persist(self, client):
        class Down(FakeClient):
            async def post(self, url, json=None, headers=None):
                if str(url).endswith("/chat"):
                    return FakeResponse(500, {"detail": "down"})
                return await FakeClient.post(self, url, json=json, headers=headers)

        import llm_client

        llm_client.httpx.AsyncClient = Down
        response = _scan(client, cid="cid-llm")
        assert response.status_code == 502
        assert db.memory().by_id == {}

    def test_duplicate_correlation_is_idempotent(self, client):
        first = _scan(client, cid="cid-same")
        calls = FakeClient.chat_calls
        second = _scan(client, cid="cid-same")
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["incident_id"] == first.json()["incident_id"]
        assert FakeClient.chat_calls == calls
        assert len(db.memory().by_id) == 1

    def test_free_is_403(self, client):
        response = _scan(client, subscription_tier="free", cid="cid-free")
        assert response.status_code == 403
        assert db.memory().by_id == {}

    def test_cross_user_incident_is_404(self, client):
        created = _scan(client, cid="cid-owner")
        incident_id = created.json()["incident_id"]
        hidden = client.get(
            f"/incidents/{incident_id}",
            params={"user_id": "user2", "subscription_tier": "premium"},
        )
        assert hidden.status_code == 404
        own = client.get("/incidents", params={"user_id": "user1", "subscription_tier": "premium"})
        assert own.status_code == 200
        assert own.json()["incidents"][0]["id"] == incident_id
        assert set(own.json()["incidents"][0]) >= {"id", "created_at", "severity", "summary", "source"}

    def test_empty_incidents_and_guidelines(self, client):
        listed = client.get(
            "/incidents",
            params={"user_id": "user1", "subscription_tier": "premium"},
        )
        guide = client.get(
            "/guidelines",
            params={"user_id": "user1", "subscription_tier": "premium"},
        )
        assert listed.status_code == 200
        assert listed.json()["incidents"] == []
        assert guide.status_code == 200
        text = guide.json()["text"]
        assert "multimodal LLM reasoning" in text
        assert "assistive" in text.lower()
