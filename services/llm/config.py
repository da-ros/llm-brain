"""LLM Service Configuration.

Settings for the LLM inference service.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """LLM service settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Service ---
    LLM_HOST: str = "0.0.0.0"
    LLM_PORT: int = 8003

    # --- LLM Provider ---
    LLM_PROVIDER: str = "bedrock"
    LLM_MODEL: str = "llama-3-8b"

    # --- AWS Bedrock ---
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    BEDROCK_MODEL_ID: str = "meta.llama3-8b-instruct-v1:0"


def get_settings() -> Settings:
    """Get settings."""
    return Settings()


settings = get_settings()