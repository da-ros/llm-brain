"""Simulator Service configuration.

Standalone FastAPI service on port 8007. Walks a decision tree, then asks
the LLM Service (Qwen3.5-4B base, temperature 0) to write each scenario.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the Simulator Service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SERVICE_NAME: str = "simulator-service"
    SERVICE_VERSION: str = "0.1.0"

    SIMULATOR_HOST: str = "0.0.0.0"
    SIMULATOR_PORT: int = 8007

    RAG_SERVICE_URL: str = "http://rag-service:8002"
    LLM_SERVICE_URL: str = "http://llm-service:8003"
    LLM_TEMPERATURE: float = 0
    LLM_MODEL_ID: str = "Qwen3.5-4B"
    RAG_TOP_K: int = 3

    RAG_TIMEOUT_SECONDS: float = 10.0
    LLM_TIMEOUT_SECONDS: float = 25.0

    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "llm_brain"
    SIMULATOR_STORE: str = "mongo"

    DEFAULT_SLEEP_HOURS: float = 7
    DEFAULT_MEETING_HOURS: float = 3
    DEFAULT_FOCUS_HOURS: float = 4
    DEFAULT_MONTHLY_SPEND: float = 0
    DEFAULT_ACTIVE_PRESCRIPTIONS: int = 0


@lru_cache
def get_settings() -> Settings:
    """Load settings (cached)."""
    return Settings()


def clear_settings_cache() -> None:
    """Drop the cached settings (used by tests)."""
    get_settings.cache_clear()
