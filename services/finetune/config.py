"""Fine-Tune Service configuration.

Local LoRA over Qwen3.5-4B (PEFT / ms-swift / Unsloth). Adapter is for the
Premium on-device build; the cloud LLM container stays base.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the Fine-Tune Service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SERVICE_NAME: str = "finetune-service"
    SERVICE_VERSION: str = "0.1.0"

    FINETUNE_HOST: str = "0.0.0.0"
    FINETUNE_PORT: int = 8004

    BASE_MODEL_ID: str = "qwen3.5-4b"
    QWEN_HF_MODEL_ID: str = "Qwen/Qwen3.5-4B"
    LORA_BACKEND: str = "peft"
    LORA_MOCK: bool = True
    LORA_MOCK_DELAY_SECONDS: float = 0.05

    TRAINING_EPOCHS: int = 5
    TRAINING_LR: float = 0.001
    MAX_TRAINING_TIME_HOURS: int = 2

    ADAPTER_OUTPUT_DIR: str = "./data/models"
    TRAINING_LOG_DIR: str = "./data/training_logs"
    ONDEVICE_MODEL_DIR: str = ""


@lru_cache
def get_settings() -> Settings:
    """Load settings (cached)."""
    return Settings()


def clear_settings_cache() -> None:
    """Drop the cached settings (used by tests)."""
    get_settings.cache_clear()


settings = get_settings()
