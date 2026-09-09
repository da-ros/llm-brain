"""Tests for LLM provider resolution (E.3). LLM HTTP calls are mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.api.config import ConfigurationError, Settings, validate_settings
from apps.api.llm.ondevice import OnDeviceProvider
from apps.api.llm.qwen_local import QwenLocalProvider
from apps.api.llm.resolver import get_provider


def test_qwen_local_provider_is_selected() -> None:
    settings = Settings(
        JWT_SECRET_KEY="present",
        LLM_PROVIDER="qwen_local",
        LLM_SERVICE_URL="http://llm-service:8003",
    )
    provider = get_provider(settings)
    assert isinstance(provider, QwenLocalProvider)
    assert provider.name == "qwen_local"


def test_local_alias_resolves_to_qwen_local() -> None:
    settings = Settings(
        JWT_SECRET_KEY="present",
        LLM_PROVIDER="local",
        LLM_SERVICE_URL="http://localhost:8003",
    )
    provider = get_provider(settings)
    assert isinstance(provider, QwenLocalProvider)


def test_ondevice_provider_is_selected() -> None:
    settings = Settings(
        JWT_SECRET_KEY="present",
        LLM_PROVIDER="ondevice",
    )
    provider = get_provider(settings)
    assert isinstance(provider, OnDeviceProvider)
    assert provider.name == "ondevice"


def test_unsupported_provider_fails_fast() -> None:
    settings = Settings(JWT_SECRET_KEY="present", LLM_PROVIDER="bedrock")
    with pytest.raises(ConfigurationError, match="Unsupported LLM_PROVIDER"):
        validate_settings(settings)


def test_qwen_local_chat_is_mocked() -> None:
    settings = Settings(
        JWT_SECRET_KEY="present",
        LLM_PROVIDER="qwen_local",
        LLM_SERVICE_URL="http://llm-service:8003",
    )
    provider = get_provider(settings)
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "hello from qwen"}
    mock_response.raise_for_status = MagicMock()
    with patch("apps.api.llm.qwen_local.httpx.post", return_value=mock_response) as mock_post:
        result = provider.chat([{"role": "user", "content": "hi"}])
    assert result == "hello from qwen"
    mock_post.assert_called_once()


def test_ondevice_chat_is_not_served_by_the_api() -> None:
    provider = OnDeviceProvider()
    with pytest.raises(RuntimeError, match="React Native"):
        provider.chat([{"role": "user", "content": "hi"}])
