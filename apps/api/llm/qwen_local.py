"""Local containerized "cloud" provider — Qwen3.5-4B **base** (not fine-tuned).

Calls the LLM Service (port 8003). Premium + RAG uses this provider.
"""

from __future__ import annotations

import httpx


class QwenLocalProvider:
    """HTTP client for the local Qwen3.5-4B base container."""

    name = "qwen_local"

    def __init__(self, base_url: str, model: str = "Qwen3.5-4B", timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def chat(self, messages: list[dict], context: str | None = None) -> str:
        payload = {"messages": messages, "context": context, "model": self.model}
        response = httpx.post(
            f"{self.base_url}/chat",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("response") or data.get("content") or ""

    def complete(self, prompt: str) -> str:
        payload = {"prompt": prompt, "model": self.model}
        response = httpx.post(
            f"{self.base_url}/generate",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("response") or data.get("content") or ""
