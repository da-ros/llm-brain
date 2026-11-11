"""Publish the on-device Q4 pack after a LoRA adapter exists."""

from __future__ import annotations

from pathlib import Path

import publish_pack
from config import get_settings
from fastapi import APIRouter, HTTPException, Request, status
from logging_setup import log_with_correlation
from pydantic import BaseModel

router = APIRouter(tags=["publish"])


class PublishRequest(BaseModel):
    user_id: str


def _safe_user(user_id: str) -> str:
    if not user_id or user_id != Path(user_id).name or user_id in {".", ".."}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user",
        )
    return user_id


@router.post("/publish", status_code=status.HTTP_202_ACCEPTED)
async def publish(request: Request, body: PublishRequest):
    """Merge this account's adapter into the iPhone GGUF and write its manifest."""
    correlation_id = getattr(request.state, "correlation_id", "no-id")
    user_id = _safe_user(body.user_id)
    adapter = Path(get_settings().ADAPTER_OUTPUT_DIR) / user_id / "adapter"
    log_with_correlation(correlation_id, "info", f"POST /publish user_id={user_id}")
    if not (adapter / "adapter_config.json").is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fine-tune this account before publishing the iPhone model.",
        )
    try:
        publish_pack.start_publish(user_id, adapter)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"status": "submitted", "phase": "preparing"}
