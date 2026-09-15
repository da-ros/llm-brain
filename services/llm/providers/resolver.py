"""LLM Provider resolver.

Backend serves premium only via the local Qwen3.5-4B container.
Free tier is on-device (Frame 10), not this service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config import get_settings
from providers.qwen_local import QwenLocalProvider

if TYPE_CHECKING:
    from providers.base import LLMProvider


def get_provider(tier: str = "premium") -> LLMProvider:
    """Select the provider for this request.

    Args:
        tier: Subscription tier. Only "premium" is served here.

    Returns:
        QwenLocalProvider for premium.

    Raises:
        ValueError: If the tier is not premium.
    """
    if tier != "premium":
        raise ValueError(
            f"Unsupported subscription tier: {tier}. "
            "Backend only supports 'premium' tier. "
            "Free tier uses on-device Qwen3.5-4B base quantized in React Native "
            "(Neural Engine / Metal, Frame 10)."
        )
    settings = get_settings()
    return QwenLocalProvider(
        model_id=settings.QWEN_MODEL_ID,
        hf_model_id=settings.QWEN_HF_MODEL_ID,
        adapter_path=settings.QWEN_ADAPTER_PATH,
        mock=settings.QWEN_MOCK,
        timeout_seconds=settings.INFERENCE_TIMEOUT_SECONDS,
    )
