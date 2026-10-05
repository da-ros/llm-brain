"""Adapter around the LLM Service HTTP API (port 8003, base Qwen3.5-4B).

ETL never talks to the model runtime directly. Document text goes to `/extract`.
A photo with no OCR text goes to `/generate` as the raw image bytes, and the
description that comes back is then sent to `/extract`.
"""

from __future__ import annotations

import base64
from typing import Any, Protocol

import httpx
from config import get_settings
from exceptions import LLMExtractionError
from logging_setup import log_with_correlation

_IMAGE_DESCRIPTION_PROMPT = (
    "Describe this image in plain sentences. "
    "Name the objects, any writing you can read, and the setting. "
    "Only state what is visible."
)
_VIDEO_DESCRIPTION_PROMPT = (
    "Describe this short video in plain sentences. "
    "Name the objects, any writing you can read, and what happens. "
    "Only state what is visible."
)


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

    def describe_media(
        self,
        payload: bytes,
        *,
        kind: str,
        filename: str = "",
        user_id: str | None = None,
        correlation_id: str = "no-id",
    ) -> str:
        """Ask the answering model what a photo or clip shows. payload is the file itself."""
        if kind not in {"image", "video"}:
            raise LLMExtractionError(f"Cannot describe {kind} bytes")
        if not payload:
            raise LLMExtractionError("Cannot describe an empty file")

        url = f"{self.base_url}/generate"
        prompt = _VIDEO_DESCRIPTION_PROMPT if kind == "video" else _IMAGE_DESCRIPTION_PROMPT
        log_with_correlation(
            correlation_id,
            "info",
            f"POST LLM Service (8003) /generate — {kind} bytes={len(payload)}",
        )
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    url,
                    json={
                        "prompt": prompt,
                        "user_id": user_id,
                        "tier": "premium",
                        "media": [
                            {
                                "kind": kind,
                                "filename": filename,
                                "content_base64": base64.b64encode(payload).decode("ascii"),
                            }
                        ],
                    },
                    headers={"X-Request-ID": correlation_id},
                )
        except httpx.TimeoutException as exc:
            raise LLMExtractionError("LLM Service inference timeout") from exc
        except httpx.HTTPError as exc:
            raise LLMExtractionError(f"LLM Service unreachable: {exc}") from exc

        if response.status_code >= 400:
            raise LLMExtractionError(
                f"LLM Service /generate failed: HTTP {response.status_code} {response.text[:300]}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise LLMExtractionError("LLM Service returned non-JSON body") from exc
        text = body.get("response") if isinstance(body, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise LLMExtractionError("The model returned an empty description")
        return text.strip()
