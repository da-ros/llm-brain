"""API Router configuration.

JWT, Kafka, MongoDB, retry, rate-limit, and downstream service URLs from the
environment / `.env`. Required secrets fail fast at startup.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the API Router."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- API ---
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    SERVICE_NAME: str = "api-gateway"
    SERVICE_VERSION: str = "0.1.0"

    # --- Auth (JWT) ---
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60

    # --- MongoDB ---
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "llm_brain"

    # --- Kafka ---
    KAFKA_ENABLED: bool = True
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_FILE_UPLOADED: str = "file.uploaded"
    KAFKA_TOPIC_TASK_RESPONSE: str = "task.response"
    KAFKA_TOPIC_DLQ: str = "task.dlq"
    KAFKA_CONSUMER_GROUP: str = "api-router"

    # --- Downstream HTTP services ---
    RAG_SERVICE_URL: str = "http://rag-service:8002"
    LLM_SERVICE_URL: str = "http://llm-service:8003"
    ETL_SERVICE_URL: str = "http://etl-service:8001"

    # --- Retry / TTL ---
    MAX_RETRIES: int = 3
    RETRY_DELAY_SECONDS: int = 5
    TASK_STATUS_TTL_DAYS: int = 30

    # --- Rate limiting (local MVP; AWS API Gateway is future / out of scope) ---
    RATE_LIMIT_UPLOAD: int = 10  # requests per minute per user
    RATE_LIMIT_CHAT: int = 30
    RATE_LIMIT_TASKS: int = 60

    # --- Upload ---
    MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024


class ConfigurationError(ValueError):
    """Raised when required configuration is missing or invalid."""


def validate_settings(settings: Settings) -> Settings:
    """Fail fast on a missing JWT secret."""
    secret = settings.JWT_SECRET_KEY.strip()
    if not secret or secret == "change-me-in-production":
        raise ConfigurationError(
            "JWT_SECRET_KEY is not configured. Set it in the environment or .env."
        )
    return settings


@lru_cache
def get_settings() -> Settings:
    """Load and validate settings (cached)."""
    return validate_settings(Settings())


def clear_settings_cache() -> None:
    """Drop the cached settings (used by tests)."""
    get_settings.cache_clear()
