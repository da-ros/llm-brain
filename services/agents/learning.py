"""Learning snapshot: batch readiness, job status, and on-device model tags."""

from __future__ import annotations

from typing import Any

import db
import httpx
from config import get_settings
from logging_setup import log_with_correlation

_ACTIVE = {"submitted", "in_progress"}


def _stamp(batch: dict[str, Any]) -> str:
    value = batch.get("updated_at") or batch.get("created_at") or ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value or "")


def _clip(text: str) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= 140:
        return cleaned
    return cleaned[:137] + "..."


def _bullets(batch: dict[str, Any] | None) -> list[str]:
    if not batch:
        return []
    lines: list[str] = []
    for item in batch.get("items") or []:
        text = _clip(str(item.get("query") or ""))
        if text and text not in lines:
            lines.append(text)
        if len(lines) == 5:
            break
    return lines


async def _refresh_job(batch: dict[str, Any], user_id: str, correlation_id: str) -> dict[str, Any]:
    """Copy Fine-Tune status onto the batch when a job id is already stored."""
    job_id = batch.get("job_id") or ""
    if not job_id or (batch.get("model_version") and batch.get("job_status") == "completed"):
        return batch
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.FINETUNE_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{settings.FINETUNE_SERVICE_URL}/status/{job_id}",
                headers={"X-Request-ID": correlation_id},
            )
    except httpx.HTTPError as exc:
        log_with_correlation(correlation_id, "warning", f"Fine-Tune status skipped: {exc}")
        return batch
    if response.status_code != 200:
        return batch
    body = response.json() or {}
    updates: dict[str, Any] = {"job_status": body.get("status") or batch.get("job_status") or ""}
    if body.get("phase"):
        updates["job_phase"] = body["phase"]
    if body.get("model_version"):
        updates["model_version"] = body["model_version"]
    stored = await db.update_batch(str(batch.get("_id") or ""), updates, user_id=user_id)
    return stored or {**batch, **updates}


async def build_learning(user_id: str, correlation_id: str) -> dict[str, Any]:
    """Counts, the open batch, the latest on-device tag, and earlier jobs."""
    settings = get_settings()
    interactions = await db.count_interactions(user_id)
    stored = await db.list_batches(user_id)
    batches = [await _refresh_job(batch, user_id, correlation_id) for batch in stored]
    batches.sort(key=_stamp, reverse=True)
    needed = settings.BATCH_MIN_ITEMS
    open_batch = next(
        (batch for batch in batches if batch.get("status") in {"accumulating", "ready"}),
        None,
    )
    trained = [batch for batch in batches if batch.get("model_version")]
    running = next(
        (
            batch
            for batch in batches
            if batch.get("job_id") and (batch.get("job_status") or "submitted") in _ACTIVE
        ),
        None,
    )
    cycles = []
    for batch in batches:
        if batch.get("status") not in {"submitted"} and not batch.get("job_id"):
            continue
        cycles.append(
            {
                "id": str(batch.get("_id") or ""),
                "version": batch.get("model_version") or "",
                "date": _stamp(batch),
                "signals": len(batch.get("items") or []),
                "status": batch.get("job_status") or "submitted",
            }
        )
    current = None
    if open_batch is not None:
        current = {
            "id": str(open_batch.get("_id") or ""),
            "status": open_batch.get("status") or "accumulating",
            "items": len(open_batch.get("items") or []),
            "needed": needed,
        }
    job = None
    if running is not None:
        job = {
            "id": running.get("job_id") or "",
            "status": running.get("job_status") or "submitted",
            "phase": running.get("job_phase") or running.get("job_status") or "submitted",
            "model_version": running.get("model_version") or "",
        }
    return {
        "interactions": interactions,
        "needed": needed,
        "model_tag": trained[0]["model_version"] if trained else "",
        "batch": current,
        "job": job,
        "learned": _bullets(trained[0] if trained else None),
        "cycles": cycles,
    }
