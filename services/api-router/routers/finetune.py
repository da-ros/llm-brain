"""Manual fine-tune trigger and on-device pack publish. Premium only."""

import json
from pathlib import Path
from typing import Annotated

import httpx
from auth import require_premium
from config import get_settings
from fastapi import APIRouter, Depends, HTTPException, Request, status
from logging_setup import log_with_correlation
from pydantic import BaseModel
from rate_limit import rate_limit_tasks
from routers.models import _directory, _load

router = APIRouter(prefix="/api", tags=["finetune"])


class FineTuneRequest(BaseModel):
    batch_id: str


@router.post("/finetune", status_code=status.HTTP_202_ACCEPTED)
async def trigger_finetune(
    request: Request,
    body: FineTuneRequest,
    user: Annotated[dict, Depends(require_premium)],
    _: Annotated[dict, Depends(rate_limit_tasks)],
):
    """Forward a ready batch to Agents POST /batches/{id}/trigger."""
    correlation_id = request.state.correlation_id
    settings = get_settings()
    log_with_correlation(
        correlation_id,
        "info",
        f"POST /api/finetune batch_id={body.batch_id}",
    )
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.AGENTS_SERVICE_URL}/batches/{body.batch_id}/trigger",
                json={
                    "user_id": user["user_id"],
                    "subscription_tier": "premium",
                },
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "error", f"Agents trigger failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Agents service error",
        ) from exc
    if response.status_code == status.HTTP_409_CONFLICT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Batch is empty, not ready, or already submitted",
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail="Fine-tune trigger failed",
        )
    data = response.json() or {}
    return {
        "job_id": data.get("job_id"),
        "status": data.get("status") or "submitted",
        "correlation_id": correlation_id,
    }


def _adapter_dir(user_id: str) -> Path:
    return Path(get_settings().ONDEVICE_MODEL_DIR).parent / "models" / user_id / "adapter"


def _adapter_ready(user_id: str) -> bool:
    return (_adapter_dir(user_id) / "adapter_config.json").is_file()


def _adapter_mtime(user_id: str) -> float | None:
    directory = _adapter_dir(user_id)
    times = [
        path.stat().st_mtime
        for path in (directory / "adapter_model.safetensors", directory / "adapter_config.json")
        if path.is_file()
    ]
    return max(times) if times else None


def _already_merged(user_id: str, directory: Path) -> bool:
    """True when the Q4 file was written after the adapter that is on disk now."""
    loaded = _load(directory)
    adapted = _adapter_mtime(user_id)
    if loaded is None or adapted is None:
        return False
    _manifest, weight = loaded
    return weight.stat().st_mtime >= adapted


def _publish_state(user_id: str) -> dict:
    directory = _directory("premium", user_id)
    body = {"status": "idle", "phase": "", "error": ""}
    status_path = directory / "publish.json"
    if status_path.is_file():
        try:
            stored = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            stored = {}
        if isinstance(stored, dict):
            body["status"] = str(stored.get("status") or body["status"])
            body["phase"] = str(stored.get("phase") or "")
            body["error"] = str(stored.get("error") or "")
    ready = _load(directory) is not None
    if ready and body["status"] == "idle":
        body["status"] = "completed"
        body["phase"] = "completed"
    return {
        "status": body["status"],
        "phase": body["phase"],
        "error": body["error"],
        "ready": ready,
        "adapter": _adapter_ready(user_id),
        "merged": _already_merged(user_id, directory),
    }


@router.get("/on-device-pack")
async def on_device_pack_status(
    request: Request,
    user: Annotated[dict, Depends(require_premium)],
) -> dict:
    """Whether this account's adapter and iPhone pack are on disk."""
    correlation_id = request.state.correlation_id
    log_with_correlation(correlation_id, "info", "GET /api/on-device-pack")
    return _publish_state(user["user_id"])


@router.post("/on-device-pack", status_code=status.HTTP_202_ACCEPTED)
async def publish_on_device_pack(
    request: Request,
    user: Annotated[dict, Depends(require_premium)],
    _: Annotated[dict, Depends(rate_limit_tasks)],
):
    """Ask the Mac trainer to merge the adapter and write the GGUF plus manifest."""
    correlation_id = request.state.correlation_id
    settings = get_settings()
    user_id = user["user_id"]
    log_with_correlation(correlation_id, "info", "POST /api/on-device-pack")
    if not _adapter_ready(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fine-tune this account before publishing the iPhone model.",
        )
    if _already_merged(user_id, _directory("premium", user_id)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This adapter is already merged.",
        )
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.FINETUNE_SERVICE_URL}/publish",
                json={"user_id": user_id},
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "error", f"Pack publish failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Fine-tune service error",
        ) from exc
    if response.status_code == status.HTTP_409_CONFLICT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pack is already being published.",
        )
    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fine-tune this account before publishing the iPhone model.",
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail="The iPhone pack could not be started.",
        )
    data = response.json() or {}
    return {
        "status": data.get("status") or "submitted",
        "phase": data.get("phase") or "preparing",
        "correlation_id": correlation_id,
    }
