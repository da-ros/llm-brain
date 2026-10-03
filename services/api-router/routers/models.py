"""On-device Q4 pack metadata and download. No LLM call and no Kafka.

The checksum is written once, when the pack is exported. The phone checks
it after download. These routes do not read the weight file to hash it again.
"""

import json
from pathlib import Path
from typing import Annotated

from config import get_settings
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from logging_setup import log_with_correlation
from rate_limit import rate_limit_model_file, rate_limit_model_metadata

router = APIRouter(prefix="/api/models", tags=["models"])

BASE_ID = "qwen3.5-4b-base-q4"
PREMIUM_ID = "qwen3.5-4b-finetuned-q4"


def _root() -> Path:
    return Path(get_settings().ONDEVICE_MODEL_DIR)


def _directory(tier: str, user_id: str) -> Path:
    if tier == "premium":
        return _root() / "users" / user_id
    return _root() / "base"


def _empty(tier: str) -> dict:
    return {
        "id": PREMIUM_ID if tier == "premium" else BASE_ID,
        "family": "Qwen3.5-4B",
        "tier": "premium" if tier == "premium" else "free",
        "quantization": "Q4",
        "parameters": "4.0B",
        "filename": "",
        "bytes": 0,
        "sha256": "",
        "ready": False,
    }


def _load(directory: Path) -> tuple[dict, Path] | None:
    """Return the manifest and weight path when the file is present and its size matches.

    `sha256` is the value stored at export. This does not open the weight file.
    """
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    filename = str(manifest.get("filename") or "")
    if not filename or filename != Path(filename).name or filename in {".", ".."}:
        return None
    weight = directory / filename
    if not weight.is_file():
        return None
    try:
        declared = int(manifest.get("bytes"))
    except (TypeError, ValueError):
        return None
    digest = str(manifest.get("sha256") or "")
    if not digest or weight.stat().st_size != declared:
        return None
    body = {
        "id": manifest.get("id"),
        "family": manifest.get("family") or "Qwen3.5-4B",
        "tier": manifest.get("tier"),
        "quantization": manifest.get("quantization") or "Q4",
        "parameters": manifest.get("parameters") or "4.0B",
        "filename": filename,
        "bytes": declared,
        "sha256": digest,
        "ready": True,
    }
    return body, weight


@router.get("/on-device")
async def on_device_metadata(
    request: Request,
    user: Annotated[dict, Depends(rate_limit_model_metadata)],
) -> dict:
    """Pack for the token plan. A client tier query is ignored."""
    correlation_id = request.state.correlation_id
    tier = user.get("subscription_tier") or "free"
    log_with_correlation(correlation_id, "info", "GET /api/models/on-device")
    loaded = _load(_directory(tier, user["user_id"]))
    if loaded is None:
        return _empty(tier)
    return loaded[0]


@router.get("/on-device/file")
async def on_device_file(
    request: Request,
    user: Annotated[dict, Depends(rate_limit_model_file)],
) -> FileResponse:
    """Stream the caller's ready pack. Does not log the bytes."""
    correlation_id = request.state.correlation_id
    tier = user.get("subscription_tier") or "free"
    log_with_correlation(correlation_id, "info", "GET /api/models/on-device/file")
    loaded = _load(_directory(tier, user["user_id"]))
    if loaded is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="On-device pack is not ready",
        )
    manifest, weight = loaded
    return FileResponse(
        weight, filename=manifest["filename"], media_type="application/octet-stream"
    )
