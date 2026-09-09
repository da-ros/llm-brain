"""Tests for GET /health (E.1)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def test_health_returns_200_with_status_ok() -> None:
    from apps.api.main import app

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["llm_provider"] in {"ondevice", "qwen_local"}


def test_health_does_not_leak_secrets() -> None:
    from apps.api.main import app

    client = TestClient(app)
    payload = json.dumps(client.get("/health").json()).lower()
    for secret_token in (
        "jwt_secret",
        "secret_key",
        "password",
        "mongodb_uri",
        "change-me",
        "test-secret-key-for-testing-only",
    ):
        assert secret_token not in payload
