"""Tests for JWT auth and the sample protected endpoint (E.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from jose import jwt

from apps.api.config import get_settings
from apps.api.store import store


def _client() -> TestClient:
    from apps.api.main import app

    return TestClient(app)


def setup_function() -> None:
    store.clear()


def test_protected_endpoint_returns_401_without_credentials() -> None:
    response = _client().get("/api/profile")
    assert response.status_code == 401


def test_register_login_and_protected_endpoint_200() -> None:
    client = _client()
    register = client.post(
        "/auth/register",
        json={
            "email": "ada@example.com",
            "password": "supersecret",
            "subscription_tier": "premium",
        },
    )
    assert register.status_code == 201
    body = register.json()
    assert "user_id" in body
    assert "password" not in body
    assert "password_hash" not in body

    login = client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "supersecret"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert login.json()["subscription_tier"] == "premium"

    profile = client.get("/api/profile", headers={"Authorization": f"Bearer {token}"})
    assert profile.status_code == 200
    assert profile.json()["email"] == "ada@example.com"


def test_duplicate_email_returns_409() -> None:
    client = _client()
    payload = {"email": "ada@example.com", "password": "supersecret"}
    assert client.post("/auth/register", json=payload).status_code == 201
    assert client.post("/auth/register", json=payload).status_code == 409


def test_expired_token_returns_401() -> None:
    client = _client()
    register = client.post(
        "/auth/register",
        json={"email": "ada@example.com", "password": "supersecret"},
    )
    user_id = register.json()["user_id"]
    settings = get_settings()
    expired = jwt.encode(
        {
            "sub": user_id,
            "subscription_tier": "free",
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    response = client.get("/api/profile", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_user_documents_are_isolated() -> None:
    client = _client()
    ada = client.post(
        "/auth/register",
        json={"email": "ada@example.com", "password": "supersecret"},
    ).json()
    bob = client.post(
        "/auth/register",
        json={"email": "bob@example.com", "password": "supersecret"},
    ).json()
    ada_token = client.post(
        "/auth/login", json={"email": "ada@example.com", "password": "supersecret"}
    ).json()["access_token"]
    bob_token = client.post(
        "/auth/login", json={"email": "bob@example.com", "password": "supersecret"}
    ).json()["access_token"]

    created = client.post(
        "/api/documents",
        json={"title": "ada-only"},
        headers={"Authorization": f"Bearer {ada_token}"},
    )
    assert created.status_code == 201
    doc_id = created.json()["document_id"]

    bob_list = client.get("/api/documents", headers={"Authorization": f"Bearer {bob_token}"})
    assert bob_list.status_code == 200
    assert bob_list.json() == []

    bob_get = client.get(
        f"/api/documents/{doc_id}",
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert bob_get.status_code == 404
    assert ada["user_id"] != bob["user_id"]
