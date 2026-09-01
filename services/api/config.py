"""Application configuration using pydantic-settings.

Reads from environment variables and .env file with safe defaults.
Validates required secrets at startup and raises clear errors when missing.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with validation and safe defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- API ---
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # --- LLM Provider ---
    LLM_PROVIDER: Literal["bedrock"] = "bedrock"
    LLM_MODEL: str = "llama-3-8b"

    # --- AWS Bedrock (premium — backend only) ---
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    BEDROCK_MODEL_ID: str = "meta.llama3-8b-instruct-v1:0"

    # --- Embeddings ---
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # --- Data stores ---
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "llm_brain"
    CHROMA_PERSIST_DIR: str = "./data/chroma"
    VECTOR_STORE_PROVIDER: Literal["chroma", "pinecone"] = "chroma"

    # --- RAG ---
    RAG_TOP_K: int = 3
    RAG_CHUNK_SIZE: int = 1000
    RAG_CHUNK_OVERLAP: int = 200

    # --- Auth (JWT + bcrypt) ---
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60

    # --- Encryption (Fernet) ---
    FERNET_KEY: str = "change-me-in-production"

    # --- Subscription tiers ---
    SUBSCRIPTION_TIER: str = "free"


def get_settings() -> Settings:
    """Get application settings with validation."""
    settings = Settings()
    # Validate required secrets at startup
    if settings.JWT_SECRET_KEY == "change-me-in-production":
        raise ValueError(
            "JWT_SECRET_KEY must be set in .env or environment. "
            "Do not use the default value in production."
        )
    if settings.FERNET_KEY == "change-me-in-production":
        raise ValueError(
            "FERNET_KEY must be set in .env or environment. "
            "Do not use the default value in production."
        )
    return settings


settings = get_settings()
