"""Tests for authentication endpoints."""

from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def test_protected_endpoint_returns_401_without_credentials():
    """Test that protected endpoint returns 401 without credentials."""
    response = client.get("/api/profile")
    assert response.status_code == 401


def test_protected_endpoint_returns_200_with_valid_token():
    """Test that protected endpoint returns 200 with valid JWT token."""
    # Create a valid JWT token for testing
    from jose import jwt
    from apps.api.config import settings

    token = jwt.encode(
        {"sub": "test-user-123", "tier": "premium"},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    response = client.get(
        "/api/profile",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "test-user-123"
    assert data["subscription_tier"] == "premium"
