"""Analytics Service configuration.

Standalone FastAPI service on port 8008. Pearson and the LLM call stay here.
The service does not load Qwen weights.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the Analytics Service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SERVICE_NAME: str = "analytics-service"
    SERVICE_VERSION: str = "0.1.0"

    ANALYTICS_HOST: str = "0.0.0.0"
    ANALYTICS_PORT: int = 8008

    RAG_SERVICE_URL: str = "http://rag-service:8002"
    LLM_SERVICE_URL: str = "http://host.docker.internal:8003"
    ETL_SERVICE_URL: str = "http://etl-service:8001"
    LLM_TEMPERATURE: float = 0
    LLM_MODEL_ID: str = "Qwen3.5-4B"

    RAG_TIMEOUT_SECONDS: float = 10.0
    LLM_TIMEOUT_SECONDS: float = 600.0
    ETL_TIMEOUT_SECONDS: float = 30.0

    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "llm_brain"
    ANALYTICS_STORE: str = "mongo"


@lru_cache
def get_settings() -> Settings:
    """Load settings (cached)."""
    return Settings()


def clear_settings_cache() -> None:
    """Drop the cached settings (used by tests)."""
    get_settings.cache_clear()
