"""Gateway Configuration.

Settings for the API Gateway service.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Gateway settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- API ---
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # --- Auth (JWT) ---
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60

    # --- MongoDB ---
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "llm_brain"

    # --- Kafka ---
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_FILE_UPLOADED: str = "file.uploaded"
    KAFKA_TOPIC_TASK_RESPONSE: str = "task.response"

    # --- Retry ---
    MAX_RETRIES: int = 3
    RETRY_DELAY_SECONDS: int = 5
    TASK_STATUS_TTL_DAYS: int = 30

    # --- Rate Limiting (AWS API GW handles this in production) ---
    RATE_LIMIT_UPLOAD: int = 10  # requests per minute
    RATE_LIMIT_CHAT: int = 30  # requests per minute
    RATE_LIMIT_TASKS: int = 60  # requests per minute


def get_settings() -> Settings:
    """Get settings with validation."""
    settings = Settings()
    if settings.JWT_SECRET_KEY == "change-me-in-production":
        raise ValueError(
            "JWT_SECRET_KEY must be set in .env or environment."
        )
    return settings


settings = get_settings()
