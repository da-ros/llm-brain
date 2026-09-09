"""Resolve the active LLM provider from `LLM_PROVIDER`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.api.config import SUPPORTED_PROVIDERS, Settings, get_settings
from apps.api.llm.ondevice import OnDeviceProvider
from apps.api.llm.qwen_local import QwenLocalProvider

if TYPE_CHECKING:
    from apps.api.llm.base import LLMProvider


def get_provider(settings: Settings | None = None) -> LLMProvider:
    """Select the provider by `LLM_PROVIDER`. Fails fast on unsupported values.

    Args:
        settings: Optional settings override (tests). Defaults to `get_settings()`.

    Returns:
        An `LLMProvider` implementation.

    Raises:
        ValueError: If `LLM_PROVIDER` is not supported.
    """
    cfg = settings or get_settings()
    name = cfg.canonical_llm_provider()

    if name == "ondevice":
        return OnDeviceProvider(variant="base")
    if name == "qwen_local":
        return QwenLocalProvider(base_url=cfg.LLM_SERVICE_URL, model=cfg.LLM_MODEL)

    supported = ", ".join((*SUPPORTED_PROVIDERS, "local (alias of qwen_local)"))
    raise ValueError(
        f"Unsupported LLM_PROVIDER={cfg.LLM_PROVIDER!r}. Supported values: {supported}."
    )
