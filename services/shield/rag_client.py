"""HTTP client for RAG POST /embed. Shield never opens Chroma."""

from __future__ import annotations

import base64

import httpx
from config import get_settings
from exceptions import EmbedTimeoutError, EmbedUpstreamError
from logging_setup import log_with_correlation


async def embed(
    *,
    modality: str,
    correlation_id: str,
    text: str = "",
    payload: bytes = b"",
) -> list[float]:
    """POST /embed. 5xx → EmbedUpstreamError, timeout → EmbedTimeoutError."""
    settings = get_settings()
    url = f"{settings.RAG_SERVICE_URL}/embed"
    body: dict[str, str] = {"modality": modality}
    if modality == "text":
        body["text"] = text
    else:
        body["content_base64"] = base64.b64encode(payload).decode("ascii")
    log_with_correlation(
        correlation_id,
        "info",
        f"RAG POST /embed {url} modality={modality}",
    )
    try:
        async with httpx.AsyncClient(timeout=settings.RAG_TIMEOUT_SECONDS) as client:
            response = await client.post(
                url,
                json=body,
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.TimeoutException as exc:
        log_with_correlation(correlation_id, "error", "RAG POST /embed timeout")
        raise EmbedTimeoutError("RAG embed timeout") from exc
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "error", f"RAG POST /embed error: {exc}")
        raise EmbedUpstreamError(f"RAG embed error: {exc}") from exc

    if response.status_code == 504:
        log_with_correlation(correlation_id, "error", "RAG POST /embed HTTP 504")
        raise EmbedTimeoutError("RAG embed timeout")
    if response.status_code >= 500:
        log_with_correlation(
            correlation_id,
            "error",
            f"RAG POST /embed HTTP {response.status_code}",
        )
        raise EmbedUpstreamError(f"RAG embed HTTP {response.status_code}")
    if response.status_code != 200:
        log_with_correlation(
            correlation_id,
            "error",
            f"RAG POST /embed HTTP {response.status_code}",
        )
        raise EmbedUpstreamError(f"RAG embed HTTP {response.status_code}")
    vector = (response.json() or {}).get("vector") or []
    if len(vector) != 2048:
        raise EmbedUpstreamError(f"RAG embed dim {len(vector)}")
    return [float(value) for value in vector]
