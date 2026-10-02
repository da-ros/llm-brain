"""HTTP client for ETL POST /parse. Analytics never parses documents itself."""

from __future__ import annotations

import httpx
from config import get_settings
from exceptions import ETLUpstreamError
from logging_setup import log_with_correlation


async def parse_text(*, filename: str, data: bytes, correlation_id: str) -> str:
    """Extracted text for this upload. Any ETL failure rejects the ingest."""
    settings = get_settings()
    url = f"{settings.ETL_SERVICE_URL}/parse"
    log_with_correlation(correlation_id, "info", f"ETL POST /parse filename={filename!r}")
    try:
        async with httpx.AsyncClient(timeout=settings.ETL_TIMEOUT_SECONDS) as client:
            response = await client.post(
                url,
                content=data,
                params={"filename": filename},
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.HTTPError as exc:
        raise ETLUpstreamError(f"ETL parse unreachable: {exc}") from exc
    if response.status_code != 200:
        raise ETLUpstreamError(f"ETL parse failed: HTTP {response.status_code}")
    return str((response.json() or {}).get("text") or "")
