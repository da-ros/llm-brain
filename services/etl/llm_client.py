"""Adapter around the LLM Service HTTP API (port 8003, base Qwen3.5-4B).

ETL never talks to the model runtime directly — it POSTs loaded content to
`/extract` and receives JSON triples.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx
from config import get_settings
from exceptions import LLMExtractionError
from logging_setup import log_with_correlation


class TripleExtractor(Protocol):
    """Minimal interface distill() depends on (ISP + DIP)."""

    def extract_triples(
        self,
        content: str,
        *,
        user_id: str | None = None,
        correlation_id: str = "no-id",
    ) -> list[dict[str, Any]]: ...


class LLMServiceClient:
    """HTTP adapter for POST {LLM_SERVICE_URL}/extract."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.LLM_SERVICE_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.LLM_TIMEOUT_SECONDS

    def extract_triples(
        self,
        content: str,
        *,
        user_id: str | None = None,
        correlation_id: str = "no-id",
    ) -> list[dict[str, Any]]:
        if not content or not content.strip():
            raise LLMExtractionError("Cannot extract triples from empty content")

        url = f"{self.base_url}/extract"
        log_with_correlation(
            correlation_id,
            "info",
            f"POST LLM Service (8003) /extract — model=Qwen3.5-4B (base) chars={len(content)}",
        )
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    url,
                    json={"content": content, "user_id": user_id, "tier": "premium"},
                    headers={"X-Request-ID": correlation_id},
                )
        except httpx.TimeoutException as exc:
            raise LLMExtractionError("LLM Service inference timeout") from exc
        except httpx.HTTPError as exc:
            raise LLMExtractionError(f"LLM Service unreachable: {exc}") from exc

        if response.status_code >= 400:
            raise LLMExtractionError(
                f"LLM Service /extract failed: HTTP {response.status_code} {response.text[:300]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise LLMExtractionError("LLM Service returned non-JSON body") from exc

        triples = payload.get("triples")
        if not isinstance(triples, list):
            raise LLMExtractionError("LLM Service response missing triples array")

        log_with_correlation(
            correlation_id,
            "info",
            f"LLM returned {len(triples)} triples",
        )
        return triples
