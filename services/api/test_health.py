"""Tests for the health endpoint."""

from fastapi.testclient import TestClient
from services.api.main import app

client = TestClient(app)


def test_health_returns_200():
    """Test that /health returns 200 with status: ok."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "llm_provider" in data


def test_health_no_secrets_leaked():
    """Test that /health does not expose secrets."""
    response = client.get("/health")
    data = response.json()
    # Should not contain API keys, passwords, or connection strings
    assert "api_key" not in data
    assert "password" not in data
    assert "secret" not in data
    assert "connection_string" not in data
