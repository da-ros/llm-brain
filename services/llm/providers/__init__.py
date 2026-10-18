"""LLM Provider layer — Protocol, local Qwen3.5-4B, Ollama, resolver."""

from providers.base import LLMProvider, LLMResult
from providers.ollama_local import OllamaProvider
from providers.qwen_local import QwenLocalProvider
from providers.resolver import get_provider

__all__ = [
    "LLMProvider",
    "LLMResult",
    "OllamaProvider",
    "QwenLocalProvider",
    "get_provider",
]
