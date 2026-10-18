"""LLM Service configuration.

LLM_BACKEND picks the runtime per machine: qwen_local runs Qwen3.5-4B in
this process (Mac: Metal), ollama talks to a local Ollama server (Linux).
LoRA adapters are for the Premium on-device build, not loaded here.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HF_HOME = _REPO_ROOT / "data" / "huggingface"


class Settings(BaseSettings):
    """Runtime settings for the LLM Service."""

    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SERVICE_NAME: str = "llm-service"
    SERVICE_VERSION: str = "0.1.0"

    LLM_HOST: str = "0.0.0.0"
    LLM_PORT: int = 8003

    # qwen_local = in-process Qwen3.5-4B (Mac/Metal). ollama = local Ollama server.
    # The default keeps CI and machines without a .env on the current behavior.
    LLM_BACKEND: str = "qwen_local"

    QWEN_MODEL_ID: str = "qwen3.5-4b"
    QWEN_HF_MODEL_ID: str = "Qwen/Qwen3.5-4B"
    QWEN_ADAPTER_PATH: str | None = None
    # Mock wins over every backend: CI and unit tests never reach a real model.
    QWEN_MOCK: bool = True
    # auto uses Metal on this Mac, CUDA when present, and refuses CPU:
    # the bfloat16 checkpoint crashes the Linux VM's CPU kernels.
    QWEN_DEVICE: str = "auto"

    OLLAMA_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "qwen3.5:4b"
    HF_HOME: str = str(_HF_HOME)
    INFERENCE_TIMEOUT_SECONDS: float = 600.0


@lru_cache
def get_settings() -> Settings:
    """Load settings (cached)."""
    return Settings()


def clear_settings_cache() -> None:
    """Drop the cached settings (used by tests)."""
    get_settings.cache_clear()


def export_hf_home() -> None:
    """Point Hugging Face at the checkpoint already stored under data/."""
    home = get_settings().HF_HOME
    os.environ.setdefault("HF_HOME", home)
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(Path(home) / "hub"))
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")


settings = get_settings()
export_hf_home()
