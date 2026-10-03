"""LLM Provider resolver.

The container serves base Qwen3.5-4B for web free and for premium.
Web free is this same model with no RAG. Phone free never calls here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config import get_settings
from providers.qwen_local import QwenLocalProvider

if TYPE_CHECKING:
    from providers.base import LLMProvider


_CLOUD_TIERS = frozenset({"free", "premium"})


def get_provider(tier: str = "premium") -> LLMProvider:
    """Select the base Qwen container for a web free or premium request.

    Args:
        tier: ``free`` or ``premium``. Both use the same base weights.
            RAG and agents stay in the API Router, not in this model.

    Returns:
        QwenLocalProvider for the base container.

    Raises:
        ValueError: If the tier is neither free nor premium.
    """
    if tier not in _CLOUD_TIERS:
        raise ValueError(
            f"Unsupported subscription tier: {tier}. "
            "Backend supports 'free' and 'premium' on the base Qwen3.5-4B container."
        )
    settings = get_settings()
    return QwenLocalProvider(
        model_id=settings.QWEN_MODEL_ID,
        hf_model_id=settings.QWEN_HF_MODEL_ID,
        adapter_path=settings.QWEN_ADAPTER_PATH,
        mock=settings.QWEN_MOCK,
        timeout_seconds=settings.INFERENCE_TIMEOUT_SECONDS,
    )
