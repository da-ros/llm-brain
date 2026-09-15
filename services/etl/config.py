"""ETL Service configuration.

Standalone FastAPI service on port 8001. Consumes file.uploaded, calls the
LLM Service (base Qwen3.5-4B on 8003) for triples, writes JSONL per user.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the ETL Service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SERVICE_NAME: str = "etl-service"
    SERVICE_VERSION: str = "0.1.0"

    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8001

    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "llm_brain"

    KAFKA_ENABLED: bool = True
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_FILE_UPLOADED: str = "file.uploaded"
    KAFKA_TOPIC_TASK_RESPONSE: str = "task.response"
    KAFKA_CONSUMER_GROUP: str = "etl-service"

    LLM_SERVICE_URL: str = "http://localhost:8003"
    LLM_TIMEOUT_SECONDS: float = 35.0

    MAX_FILE_SIZE: int = 10 * 1024 * 1024
    TRIPLES_OUTPUT_DIR: str = "./data/triples"


@lru_cache
def get_settings() -> Settings:
    """Load settings (cached)."""
    return Settings()


def clear_settings_cache() -> None:
    """Drop the cached settings (used by tests)."""
    get_settings.cache_clear()
