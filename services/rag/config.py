"""RAG Service Configuration.

Settings for the RAG microservice.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """RAG service settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- API ---
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8002

    # --- MongoDB ---
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "llm_brain"

    # --- Vector Store ---
    VECTOR_STORE_PROVIDER: Literal["chroma", "pinecone"] = "chroma"
    CHROMA_PERSIST_DIR: str = "./data/chroma"

    # --- Embeddings ---
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # --- RAG ---
    RAG_TOP_K: int = 3
    RAG_CHUNK_SIZE: int = 1000
    RAG_CHUNK_OVERLAP: int = 200

    # --- Encryption ---
    FERNET_KEY: str = "change-me-in-production"


def get_settings() -> Settings:
    """Get settings with validation."""
    settings = Settings()
    if settings.FERNET_KEY == "change-me-in-production":
        raise ValueError("FERNET_KEY must be set in .env or environment.")
    return settings


settings = get_settings()
