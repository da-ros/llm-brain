"""Agents Service configuration.

Standalone FastAPI service on port 8006. Orchestrates Ingestor / Razonador /
Evaluador with LangGraph. Calls RAG, LLM, and Fine-Tune over HTTP only.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the Agents Service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SERVICE_NAME: str = "agents-service"
    SERVICE_VERSION: str = "0.1.0"
    ORCHESTRATOR: str = "langgraph"

    AGENTS_HOST: str = "0.0.0.0"
    AGENTS_PORT: int = 8006

    RAG_SERVICE_URL: str = "http://rag-service:8002"
    LLM_SERVICE_URL: str = "http://host.docker.internal:8003"
    FINETUNE_SERVICE_URL: str = "http://finetune-service:8004"
    SIMULATOR_SERVICE_URL: str = "http://simulator-service:8007"
    SHIELD_SERVICE_URL: str = "http://shield-service:8009"
    ANALYTICS_SERVICE_URL: str = "http://analytics-service:8008"

    RAG_TIMEOUT_SECONDS: float = 10.0
    LLM_TIMEOUT_SECONDS: float = 600.0
    FINETUNE_TIMEOUT_SECONDS: float = 15.0
    SIMULATOR_TIMEOUT_SECONDS: float = 30.0
    SHIELD_TIMEOUT_SECONDS: float = 30.0
    ANALYTICS_TIMEOUT_SECONDS: float = 30.0

    KAFKA_ENABLED: bool = True
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_SESSION_TURN: str = "session.turn.completed"
    KAFKA_CONSUMER_GROUP: str = "agents-service"

    EVAL_SCORE_THRESHOLD: float = 0.6
    BATCH_MIN_ITEMS: int = 10
    BATCH_EXPORT_DIR: str = "./data/finetune_batches"

    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "llm_brain"
    AGENTS_STORE: str = "mongo"
    TASK_STATUS_TTL_DAYS: int = 30


@lru_cache
def get_settings() -> Settings:
    """Load settings (cached)."""
    return Settings()


def clear_settings_cache() -> None:
    """Drop the cached settings (used by tests)."""
    get_settings.cache_clear()
