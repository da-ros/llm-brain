"""ETL Service Configuration.

Settings for the ETL microservice.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """ETL service settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- API ---
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8001

    # --- MongoDB ---
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "llm_brain"

    # --- Kafka ---
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_FILE_UPLOADED: str = "file.uploaded"
    KAFKA_TOPIC_TASK_RESPONSE: str = "task.response"

    # --- ETL ---
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    TRIPLES_OUTPUT_DIR: str = "./data/triples"


def get_settings() -> Settings:
    """Get settings."""
    return Settings()


settings = get_settings()
