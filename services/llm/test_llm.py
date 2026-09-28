"""Tests for LLM Service — local Qwen3.5-4B provider, resolver, endpoints."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

os.environ["QWEN_MOCK"] = "true"
os.environ["QWEN_MODEL_ID"] = "qwen3.5-4b"


class TestConfig:
    """Tests for LLM service configuration."""

    def test_config_defaults(self):
        from config import Settings

        s = Settings()
        assert s.LLM_PORT == 8003
        assert s.QWEN_MODEL_ID == "qwen3.5-4b"
        assert s.QWEN_ADAPTER_PATH is None
        assert s.SERVICE_NAME == "llm-service"


class TestProviderProtocol:
    """G.1 — LLMProvider protocol with mock local Qwen."""

    def test_qwen_local_satisfies_protocol(self):
        from providers.base import LLMProvider
        from providers.qwen_local import QwenLocalProvider

        provider = QwenLocalProvider(mock=True)
        assert isinstance(provider, LLMProvider)

    def test_complete_returns_tokens(self):
        from providers.qwen_local import QwenLocalProvider

        provider = QwenLocalProvider(mock=True)
        result = provider.complete("¿Cuándo debo tomar la medicina?")
        assert result.text.startswith("[Qwen3.5-4B base]")
        assert result.tokens_used > 0

    def test_chat_with_context_and_multimodal(self):
        from providers.qwen_local import QwenLocalProvider

        provider = QwenLocalProvider(mock=True)
        result = provider.chat(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is on this photo?"},
                        {"type": "image", "url": "s3://receta.png"},
                    ],
                }
            ],
            context="Receta: Ibuprofeno 400mg",
        )
        assert "Ibuprofeno" in result.text
        assert "[image:" in result.text
        assert result.tokens_used > 0

    def test_extract_triples_mock(self):
        from providers.qwen_local import QwenLocalProvider

        provider = QwenLocalProvider(mock=True)
        triples, tokens = provider.extract_triples("Ibuprofeno trata el dolor.")
        assert triples
        assert triples[0]["subject"]
        assert triples[0]["predicate"]
        assert triples[0]["object"]
        assert tokens > 0

    def test_parse_triples_json(self):
        from providers.qwen_local import parse_triples_json

        raw = '[{"subject": "Ibuprofeno", "predicate": "trata", "object": "dolor"}]'
        triples = parse_triples_json(raw)
        assert triples[0]["object"] == "dolor"


class TestProviderResolver:
    """G.2 — resolver selects local Qwen for premium; rejects free."""

    def test_premium_resolves_to_qwen_local(self):
        from providers.qwen_local import QwenLocalProvider
        from providers.resolver import get_provider

        provider = get_provider("premium")
        assert isinstance(provider, QwenLocalProvider)
        assert provider.mock is True

    def test_free_tier_raises(self):
        from providers.resolver import get_provider

        with pytest.raises(ValueError, match="Unsupported subscription tier"):
            get_provider("free")

    def test_unknown_tier_raises(self):
        from providers.resolver import get_provider

        with pytest.raises(ValueError, match="Unsupported subscription tier"):
            get_provider("unknown")


class TestHealthEndpoint:
    def test_health_reports_local_qwen(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "llm-service"
        assert data["provider"] == "qwen-local-container"
        assert data["model"] == "qwen3.5-4b"
        assert "api_key" not in data
        assert "secret" not in data


class TestGenerateEndpoint:
    """G.3 — POST /generate with mocked local Qwen3.5-4B."""

    def test_generate_returns_response_and_tokens(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/generate",
            json={"prompt": "¿Cuándo debo tomar la medicina?", "user_id": "user-123"},
            headers={"X-Request-ID": "abc-123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert isinstance(data["tokens_used"], int)
        assert data["tokens_used"] > 0
        assert response.headers.get("X-Request-ID") == "abc-123"

    def test_generate_missing_prompt_returns_400(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post("/generate", json={"user_id": "u1"})
        assert response.status_code == 400

    def test_generate_empty_prompt_returns_400(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post("/generate", json={"prompt": "   ", "user_id": "u1"})
        assert response.status_code == 400

    def test_generate_free_tier_returns_400(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/generate",
            json={"prompt": "hello", "user_id": "u1", "tier": "free"},
        )
        assert response.status_code == 400

    def test_generate_timeout_returns_504(self):
        from fastapi.testclient import TestClient
        from main import app
        from providers.qwen_local import QwenLocalProvider

        def boom(self, prompt: str):
            raise TimeoutError("slow")

        with patch.object(QwenLocalProvider, "complete", boom):
            client = TestClient(app)
            response = client.post(
                "/generate",
                json={"prompt": "hello", "user_id": "u1"},
            )
        assert response.status_code == 504

    def test_generate_unavailable_returns_500(self):
        from exceptions import ModelUnavailableError
        from fastapi.testclient import TestClient
        from main import app
        from providers.qwen_local import QwenLocalProvider

        def boom(self, prompt: str):
            raise ModelUnavailableError("Qwen3.5-4B container unavailable")

        with patch.object(QwenLocalProvider, "complete", boom):
            client = TestClient(app)
            response = client.post(
                "/generate",
                json={"prompt": "hello", "user_id": "u1"},
            )
        assert response.status_code == 500


class TestChatEndpoint:
    """G.4 — POST /chat with mocked local Qwen3.5-4B."""

    def test_chat_returns_response_and_tokens(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/chat",
            json={
                "messages": [{"role": "user", "content": "¿Qué debo comprar esta semana?"}],
                "context": "Receta: Ibuprofeno 400mg, 3 veces al día",
                "user_id": "user-123",
            },
            headers={"X-Request-ID": "def-456"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert data["tokens_used"] > 0
        assert "Ibuprofeno" in data["response"]

    def test_chat_missing_messages_returns_400(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post("/chat", json={"user_id": "u1"})
        assert response.status_code == 400

    def test_chat_free_tier_returns_400(self):
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
        )
        assert response.status_code == 400


class TestExtractEndpoint:
    def test_extract_returns_triples(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/extract",
            json={"content": "Ibuprofeno trata el dolor.", "user_id": "user-123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["triples"]
        assert data["tokens_used"] > 0
        assert "subject" in data["triples"][0]


def test_settings_cache_reset():
    from config import clear_settings_cache, get_settings

    clear_settings_cache()
    s = get_settings()
    assert s.QWEN_MODEL_ID == "qwen3.5-4b"


# ── Extract endpoint coverage ─────────────────────────────────────


class TestExtractCoverage:
    def test_extract_empty_content(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post("/extract", json={"content": "", "user_id": "u1"})
        assert response.status_code == 400

    def test_extract_whitespace_content(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post("/extract", json={"content": "   ", "user_id": "u1"})
        assert response.status_code == 400

    def test_extract_missing_content(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post("/extract", json={"user_id": "u1"})
        assert response.status_code == 400

    def test_extract_invalid_tier(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/extract",
            json={"content": "test content", "user_id": "u1", "tier": "invalid"},
        )
        assert response.status_code == 400


# ── Chat endpoint coverage ────────────────────────────────────────


class TestChatCoverage:
    def test_chat_empty_messages(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post("/chat", json={"messages": [], "user_id": "u1"})
        assert response.status_code == 400

    def test_chat_missing_messages(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post("/chat", json={"user_id": "u1"})
        assert response.status_code == 400

    def test_chat_missing_user_id(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/chat", json={"messages": [{"role": "user", "content": "hi"}]}
        )
        assert response.status_code == 400

    def test_chat_invalid_tier(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/chat",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "user_id": "u1",
                "tier": "invalid",
            },
        )
        assert response.status_code == 400

    def test_chat_success(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/chat",
            json={
                "messages": [{"role": "user", "content": "hello"}],
                "user_id": "u1",
            },
        )
        assert response.status_code == 200
        assert "response" in response.json()

    def test_chat_with_context(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/chat",
            json={
                "messages": [{"role": "user", "content": "hello"}],
                "user_id": "u1",
                "context": "some RAG context",
            },
        )
        assert response.status_code == 200
