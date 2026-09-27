"""Environment-based configuration for the platform foundation.

Loads settings from the environment / `.env` via pydantic-settings.
Optional values have documented defaults. Required secrets and an
unsupported `LLM_PROVIDER` fail fast at startup.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

SUPPORTED_PROVIDERS = ("ondevice", "qwen_local")
# CI and older env files used `local` as the containerized Qwen provider.
PROVIDER_ALIASES = {"local": "qwen_local"}


class Settings(BaseSettings):
    """Runtime settings for `apps.api`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- API ---
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # --- Auth (JWT + bcrypt) ---
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60

    # --- LLM ---
    LLM_PROVIDER: str = "qwen_local"
    LLM_MODEL: str = "Qwen3.5-4B"
    LLM_SERVICE_URL: str = "http://localhost:8003"

    # --- Data stores (used by later modules; safe defaults here) ---
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "llm_brain"
    CHROMA_PERSIST_DIR: str = "./data/chroma"

    def canonical_llm_provider(self) -> str:
        """Return the resolved provider name (`ondevice` or `qwen_local`)."""
        raw = self.LLM_PROVIDER.strip().lower()
        return PROVIDER_ALIASES.get(raw, raw)


class ConfigurationError(ValueError):
    """Raised when required configuration is missing or invalid."""


def validate_settings(settings: Settings) -> Settings:
    """Fail fast on missing secrets or an unsupported LLM provider."""
    if not settings.JWT_SECRET_KEY.strip():
        raise ConfigurationError(
            "JWT_SECRET_KEY is not configured. Set it in the environment or .env."
        )

    provider = settings.canonical_llm_provider()
    if provider not in SUPPORTED_PROVIDERS:
        supported = ", ".join((*SUPPORTED_PROVIDERS, "local (alias of qwen_local)"))
        raise ConfigurationError(
            f"Unsupported LLM_PROVIDER={settings.LLM_PROVIDER!r}. Supported values: {supported}."
        )

    if provider == "qwen_local" and not settings.LLM_SERVICE_URL.strip():
        raise ConfigurationError(
            "LLM_SERVICE_URL is required when LLM_PROVIDER=qwen_local "
            "(URL of the Qwen3.5-4B base container, typically http://localhost:8003)."
        )

    return settings


@lru_cache
def get_settings() -> Settings:
    """Load and validate settings (cached)."""
    return validate_settings(Settings())


def clear_settings_cache() -> None:
    """Drop the cached settings (used by tests)."""
    get_settings.cache_clear()
