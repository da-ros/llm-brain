"""Tests for LLM provider resolution."""

import pytest

from apps.api.llm.bedrock import BedrockProvider
from apps.api.llm.resolver import get_provider


def test_provider_resolution_premium_tier():
    """Test that premium tier resolves to BedrockProvider."""
    provider = get_provider("premium")
    assert isinstance(provider, BedrockProvider)


def test_provider_resolution_unsupported_tier():
    """Test that unsupported tier fails fast."""
    with pytest.raises(ValueError, match="Unsupported subscription tier"):
        get_provider("free")


def test_provider_resolution_unknown_tier():
    """Test that unknown tier fails fast."""
    with pytest.raises(ValueError, match="Unsupported subscription tier"):
        get_provider("unknown")
