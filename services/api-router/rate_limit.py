"""In-memory per-user rate limiting for the local MVP.

AWS API Gateway rate limiting is future / out of scope. This limiter is
process-local and resets on restart — acceptable for a single-node Compose stack.
"""

import threading
import time
from typing import Annotated

from auth import verify_token
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
