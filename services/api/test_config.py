"""Tests for configuration."""

import os
from unittest.mock import patch

import pytest


def test_config_falls_back_to_defaults():
    """Test that config falls back to defaults when optional variables are absent."""
    # Clear optional env vars
    env_vars = {k: v for k, v in os.environ.items() if k not in ["API_PORT", "API_HOST"]}

    with patch.dict(os.environ, env_vars, clear=True):
        from services.api.config import Settings
        settings = Settings()
        assert settings.API_PORT == 8000
        assert settings.API_HOST == "0.0.0.0"


def test_config_fails_fast_on_missing_required_secret():
    """Test that config fails fast when required secrets are missing."""
    # Mock the settings to use default (invalid) secrets
    with patch.dict(os.environ, {
        "JWT_SECRET_KEY": "change-me-in-production",
        "FERNET_KEY": "change-me-in-production",
    }, clear=True):
        from services.api.config import get_settings
        with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
            get_settings()
