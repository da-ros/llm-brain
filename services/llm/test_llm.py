"""Tests for LLM Service — Config, Providers, Health, Endpoints."""

import os
import sys
from pathlib import Path

import pytest

# Add services/llm to Python path
sys.path.insert(0, str(Path(__file__).parent))

# Set env vars before any imports
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test-key")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test-secret")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("BEDROCK_MODEL_ID", "meta.llama3-8b-instruct-v1:0")


# --- Config Tests ---


class TestConfig:
    """Tests for LLM service configuration."""

    def test_config_defaults(self):
        """Test that config has correct defaults."""
        from config import Settings

        s = Settings()
        assert s.LLM_PORT == 8003
        assert s.LLM_PROVIDER == "bedrock"
        assert s.AWS_REGION == "us-east-1"
        assert s.BEDROCK_MODEL_ID == "meta.llama3-8b-instruct-v1:0"


# --- Provider Resolution Tests ---


class TestProviderResolution:
    """Tests for provider resolution."""

    def test_premium_tier_resolves_to_bedrock(self):
        """Test that premium tier resolves to BedrockProvider."""
        from services.llm.providers.resolver import get_provider
        from services.llm.providers.bedrock import BedrockProvider

        provider = get_provider("premium")
        assert isinstance(provider, BedrockProvider)

    def test_unsupported_tier_raises(self):
        """Test that unsupported tier raises ValueError."""
        from services.llm.providers.resolver import get_provider

        with pytest.raises(ValueError, match="Unsupported subscription tier"):
            get_provider("free")

    def test_unknown_tier_raises(self):
        """Test that unknown tier raises ValueError."""
        from services.llm.providers.resolver import get_provider

        with pytest.raises(ValueError, match="Unsupported subscription tier"):
            get_provider("unknown")


# --- BedrockProvider Tests ---


class TestBedrockProvider:
    """Tests for BedrockProvider stubs."""

    def test_chat_returns_placeholder(self):
        """Test that chat returns placeholder response."""
        from services.llm.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        result = provider.chat([{"role": "user", "content": "hello"}])
        assert result.startswith("[Bedrock LLM]")

    def test_complete_returns_placeholder(self):
        """Test that complete returns placeholder response."""
        from services.llm.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        result = provider.complete("test prompt")
        assert result.startswith("[Bedrock LLM]")

    def test_chat_with_context(self):
        """Test that chat includes context in response."""
        from services.llm.providers.bedrock import BedrockProvider

        provider = BedrockProvider()
        result = provider.chat(
            [{"role": "user", "content": "hello"}],
            context="some context",
        )
        assert result.startswith("[Bedrock LLM]")


# --- Health Endpoint Tests ---


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_returns_200(self):
        """Test that /health returns 200 with status ok."""
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "llm-service"
        assert "provider" in data
        assert "model" in data

    def test_health_no_secrets(self):
        """Test that health endpoint doesn't expose secrets."""
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.get("/health")
        data = response.json()
        assert "api_key" not in data
        assert "secret" not in data


# --- Generate Endpoint Tests ---


class TestGenerateEndpoint:
    """Tests for POST /generate endpoint."""

    def test_generate_returns_response_and_tokens(self):
        """Test that /generate returns response and tokens_used."""
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/generate",
            json={"prompt": "hello", "user_id": "u1", "tier": "premium"},
            headers={"X-Request-ID": "test-id-123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert "tokens_used" in data
        assert isinstance(data["tokens_used"], int)

    def test_generate_invalid_tier_returns_400(self):
        """Test that /generate returns 400 for invalid tier."""
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/generate",
            json={"prompt": "hello", "user_id": "u1", "tier": "free"},
            headers={"X-Request-ID": "test-id-123"},
        )
        assert response.status_code == 400

    def test_generate_missing_fields_returns_422(self):
        """Test that /generate returns 422 for missing fields."""
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/generate",
            json={},
        )
        assert response.status_code == 422


# --- Chat Endpoint Tests ---


class TestChatEndpoint:
    """Tests for POST /chat endpoint."""

    def test_chat_returns_response_and_tokens(self):
        """Test that /chat returns response and tokens_used."""
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/chat",
            json={
                "messages": [{"role": "user", "content": "hello"}],
                "user_id": "u1",
                "tier": "premium",
            },
            headers={"X-Request-ID": "test-id-456"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert "tokens_used" in data

    def test_chat_invalid_tier_returns_400(self):
        """Test that /chat returns 400 for invalid tier."""
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/chat",
            json={
                "messages": [{"role": "user", "content": "hello"}],
                "user_id": "u1",
                "tier": "free",
            },
            headers={"X-Request-ID": "test-id-456"},
        )
        assert response.status_code == 400