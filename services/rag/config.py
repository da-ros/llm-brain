"""RAG Service configuration.

Standalone FastAPI service on port 8002. Local MongoDB/GridFS + Chroma,
Qwen3-VL-Embedding-2B (2048-dim, multimodal), Fernet at application level.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the RAG Service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SERVICE_NAME: str = "rag-service"
    SERVICE_VERSION: str = "0.1.0"

    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8002

    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "llm_brain"
    MONGODB_MAX_POOL_SIZE: int = 50
    MONGODB_MIN_POOL_SIZE: int = 1

    VECTOR_STORE_PROVIDER: Literal["chroma"] = "chroma"
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8005
    CHROMA_COLLECTION: str = "llm_brain_embeddings"

    EMBEDDING_MODEL: str = "Qwen/Qwen3-VL-Embedding-2B"
    EMBEDDING_DIM: int = 2048
    EMBEDDING_MOCK: bool = True

    RAG_TOP_K: int = 8
    RAG_CHUNK_SIZE: int = 1000
    RAG_CHUNK_OVERLAP: int = 200

    # Default = urlsafe_b64(sha256("FERNET_KEY@TESIS_MESTRIA_UPS")) — valid Fernet key for local dev.
    # Production: stable key from the secret store. Rotating the key makes stored ciphertext unreadable.
    FERNET_KEY: str = "JEWS9jt7GqTkkv1N8y-Kld5V8IeFZMw_UFFhn4h-xsU="


def fernet_key_bytes(raw: str | None = None) -> bytes:
    """Return a 32-byte url-safe Fernet key, deriving one if the env value is not valid."""
    from cryptography.fernet import Fernet

    value = (raw if raw is not None else get_settings().FERNET_KEY).encode("utf-8")
    try:
        Fernet(value)
        return value
    except (ValueError, Exception):
        digest = hashlib.sha256(value).digest()
        return base64.urlsafe_b64encode(digest)


@lru_cache
def get_settings() -> Settings:
    """Load settings (cached)."""
    return Settings()


def clear_settings_cache() -> None:
    """Drop the cached settings (used by tests)."""
    get_settings.cache_clear()
