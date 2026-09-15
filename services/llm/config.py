"""LLM Service configuration.

Local Qwen3.5-4B base container ("cloud" = this process). LoRA adapters are
for the Premium on-device build (Frame 10), not loaded here.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the LLM Service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SERVICE_NAME: str = "llm-service"
    SERVICE_VERSION: str = "0.1.0"

    LLM_HOST: str = "0.0.0.0"
    LLM_PORT: int = 8003

    QWEN_MODEL_ID: str = "qwen3.5-4b"
    QWEN_HF_MODEL_ID: str = "Qwen/Qwen3.5-4B"
    QWEN_ADAPTER_PATH: str | None = None
    QWEN_MOCK: bool = True
    INFERENCE_TIMEOUT_SECONDS: float = 30.0


@lru_cache
def get_settings() -> Settings:
    """Load settings (cached)."""
    return Settings()


def clear_settings_cache() -> None:
    """Drop the cached settings (used by tests)."""
    get_settings.cache_clear()


settings = get_settings()
