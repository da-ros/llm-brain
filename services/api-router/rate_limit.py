"""In-memory per-user rate limiting for the local MVP.

AWS API Gateway rate limiting is future / out of scope. This limiter is
process-local and resets on restart — acceptable for a single-node Compose stack.
"""

import threading
import time
from typing import Annotated

from auth import require_premium, verify_token
from config import get_settings
from fastapi import Depends, HTTPException, status


class InMemoryRateLimiter:
    """Sliding-window limiter keyed by an arbitrary string."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: int = 60) -> bool:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            recent = [stamp for stamp in self._hits.get(key, []) if stamp > cutoff]
            if len(recent) >= limit:
                self._hits[key] = recent
                return False
            recent.append(now)
            self._hits[key] = recent
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = InMemoryRateLimiter()


def _enforce(user: dict, bucket: str, limit: int) -> dict:
    key = f"{bucket}:{user['user_id']}"
    if not limiter.allow(key, limit):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )
    return user


def rate_limit_upload(user: Annotated[dict, Depends(verify_token)]) -> dict:
    return _enforce(user, "upload", get_settings().RATE_LIMIT_UPLOAD)


def rate_limit_chat(user: Annotated[dict, Depends(verify_token)]) -> dict:
    return _enforce(user, "chat", get_settings().RATE_LIMIT_CHAT)


def rate_limit_tasks(user: Annotated[dict, Depends(verify_token)]) -> dict:
    return _enforce(user, "tasks", get_settings().RATE_LIMIT_TASKS)


def rate_limit_simulate(user: Annotated[dict, Depends(require_premium)]) -> dict:
    """Premium gate first, then 10 simulate requests per minute. Free stays 403."""
    return _enforce(user, "simulate", get_settings().RATE_LIMIT_SIMULATE)


def rate_limit_shield(user: Annotated[dict, Depends(require_premium)]) -> dict:
    """Premium gate first, then 30 shield scans per minute. Free stays 403."""
    return _enforce(user, "shield", get_settings().RATE_LIMIT_SHIELD_SCAN)


def rate_limit_analytics_ingest(user: Annotated[dict, Depends(require_premium)]) -> dict:
    """Premium gate first, then 10 analytics ingests per minute. Free stays 403."""
    return _enforce(user, "analytics-ingest", get_settings().RATE_LIMIT_ANALYTICS_INGEST)


def rate_limit_analytics_query(user: Annotated[dict, Depends(require_premium)]) -> dict:
    """Premium gate first, then 30 correlation reads per minute. Free stays 403."""
    return _enforce(user, "analytics-query", get_settings().RATE_LIMIT_ANALYTICS_QUERY)


def rate_limit_model_metadata(user: Annotated[dict, Depends(verify_token)]) -> dict:
    return _enforce(user, "model-metadata", get_settings().RATE_LIMIT_MODEL_METADATA)


def rate_limit_model_file(user: Annotated[dict, Depends(verify_token)]) -> dict:
    return _enforce(user, "model-file", get_settings().RATE_LIMIT_MODEL_FILE)
