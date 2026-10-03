"""Shield Service configuration.

Standalone FastAPI service on port 8009. Heuristics and embedding similarity
are evidence. Qwen3.5-4B (temperature 0) states the scam likelihood.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_corpus() -> Path:
    """Locate data/shield/corpus.jsonl walking up from this file.

    Repo layout is <root>/services/shield/config.py; the container layout is
    /app/config.py with the data volume mounted (CORPUS_PATH env overrides
    this default). Walking up avoids IndexError on the shallow container path.
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "data" / "shield" / "corpus.jsonl"
        if candidate.exists():
            return candidate
    return Path("data/shield/corpus.jsonl")


_DEFAULT_CORPUS = _default_corpus()


class Settings(BaseSettings):
    """Runtime settings for the Shield Service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SERVICE_NAME: str = "shield-service"
    SERVICE_VERSION: str = "0.1.0"

    SHIELD_HOST: str = "0.0.0.0"
    SHIELD_PORT: int = 8009

    RAG_SERVICE_URL: str = "http://rag-service:8002"
    LLM_SERVICE_URL: str = "http://llm-service:8003"
    LLM_TEMPERATURE: float = 0
    LLM_MODEL_ID: str = "Qwen3.5-4B"

    RAG_TIMEOUT_SECONDS: float = 10.0
    LLM_TIMEOUT_SECONDS: float = 25.0

    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "llm_brain"
    SHIELD_STORE: str = "mongo"

    SIMILARITY_THRESHOLD: float = 0.80
    MAX_UPLOAD_BYTES: int = 20 * 1024 * 1024
    CORPUS_PATH: str = str(_DEFAULT_CORPUS)


@lru_cache
def get_settings() -> Settings:
    """Load settings (cached)."""
    return Settings()


def clear_settings_cache() -> None:
    """Drop the cached settings (used by tests)."""
    get_settings.cache_clear()
