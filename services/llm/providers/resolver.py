"""LLM Provider resolver.

LLM_BACKEND picks the runtime per machine (qwen_local | ollama); QWEN_MOCK=true
always wins so CI and unit tests never reach a real model.
Web free is the same base model with no RAG. Phone free never calls here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config import get_settings
from providers.ollama_local import OllamaProvider
from providers.qwen_local import QwenLocalProvider

if TYPE_CHECKING:
    from providers.base import LLMProvider


_CLOUD_TIERS = frozenset({"free", "premium"})
_provider: LLMProvider | None = None


def _build_provider() -> LLMProvider:
    """Create the provider for this machine's backend. Mock short-circuits."""
    settings = get_settings()
    if settings.QWEN_MOCK:
        # CI and unit tests: no weights, no sockets, whatever .env says.
        return QwenLocalProvider(
            model_id=settings.QWEN_MODEL_ID,
            hf_model_id=settings.QWEN_HF_MODEL_ID,
            adapter_path=settings.QWEN_ADAPTER_PATH,
            mock=True,
            timeout_seconds=settings.INFERENCE_TIMEOUT_SECONDS,
        )
    backend = (settings.LLM_BACKEND or "qwen_local").strip().lower()
    if backend in {"ollama", "ollama_local"}:
        return OllamaProvider(
            model=settings.OLLAMA_MODEL,
            url=settings.OLLAMA_URL,
            mock=False,
            timeout_seconds=settings.INFERENCE_TIMEOUT_SECONDS,
            think=settings.OLLAMA_THINK,
        )
    if backend not in {"qwen_local", "local"}:
        raise ValueError(
            f"Unsupported LLM_BACKEND: {settings.LLM_BACKEND}. "
            "Supported values: 'qwen_local' and 'ollama'."
        )
    return QwenLocalProvider(
        model_id=settings.QWEN_MODEL_ID,
        hf_model_id=settings.QWEN_HF_MODEL_ID,
        adapter_path=settings.QWEN_ADAPTER_PATH,
        mock=False,
        timeout_seconds=settings.INFERENCE_TIMEOUT_SECONDS,
    )


def get_provider(tier: str = "premium") -> LLMProvider:
    """Select the base model process for a web free or premium request.

    The loaded weights stay on the first provider. A new object per request
    would read the 9 GB checkpoint again.

    Args:
        tier: ``free`` or ``premium``. Both use the same base model.
            RAG and agents stay in the API Router, not in this model.

    Returns:
        The provider for this machine's LLM_BACKEND.

    Raises:
        ValueError: If the tier is neither free nor premium, or the
            configured LLM_BACKEND is unknown.
    """
    global _provider
    if tier not in _CLOUD_TIERS:
        raise ValueError(
            f"Unsupported subscription tier: {tier}. "
            "Backend supports 'free' and 'premium' on the base Qwen3.5-4B checkpoint."
        )
    if _provider is None:
        _provider = _build_provider()
    return _provider
