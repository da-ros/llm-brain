"""Tests for configuration defaults and fail-fast (E.2)."""

from __future__ import annotations

import pytest

from apps.api.config import (
    ConfigurationError,
    Settings,
    clear_settings_cache,
    get_settings,
    validate_settings,
)


def test_optional_values_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("API_PORT", raising=False)
    monkeypatch.delenv("API_HOST", raising=False)
    settings = Settings()
    assert settings.API_PORT == 8000
    assert settings.API_HOST == "0.0.0.0"
    assert settings.LLM_MODEL == "Qwen3.5-4B"


def test_missing_jwt_secret_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "")
    settings = Settings()
    with pytest.raises(ConfigurationError, match="JWT_SECRET_KEY"):
        validate_settings(settings)


def test_missing_llm_service_url_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "present")
    monkeypatch.setenv("LLM_PROVIDER", "qwen_local")
    monkeypatch.setenv("LLM_SERVICE_URL", "")
    settings = Settings()
    with pytest.raises(ConfigurationError, match="LLM_SERVICE_URL"):
        validate_settings(settings)


def test_get_settings_fails_fast_on_empty_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "")
    clear_settings_cache()
    with pytest.raises(ConfigurationError, match="JWT_SECRET_KEY"):
        get_settings()
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-testing-only")
    clear_settings_cache()
