"""Fine-Tune Service Configuration.

Settings for the LoRA fine-tuning service.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Fine-Tune service settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Service ---
    FINETUNE_HOST: str = "0.0.0.0"
    FINETUNE_PORT: int = 8004

    # --- AWS Bedrock ---
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    BEDROCK_MODEL_ID: str = "meta.llama3-8b-instruct-v1:0"

    # --- Training ---
    TRAINING_MAX_EPOCHS: int = 3
    TRAINING_LEARNING_RATE: float = 1e-5
    TRAINING_MAX_TIME: int = 3600  # seconds
    TRAINING_OUTPUT_DIR: str = "./data/training"


def get_settings() -> Settings:
    """Get settings."""
    return Settings()


settings = get_settings()