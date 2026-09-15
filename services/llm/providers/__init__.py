"""LLM Provider layer — Protocol, local Qwen3.5-4B, resolver."""

from providers.base import LLMProvider, LLMResult
from providers.qwen_local import QwenLocalProvider
from providers.resolver import get_provider

__all__ = ["LLMProvider", "LLMResult", "QwenLocalProvider", "get_provider"]
