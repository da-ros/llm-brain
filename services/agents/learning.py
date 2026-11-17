"""Learning snapshot: batch readiness, job status, and on-device model tags."""

from __future__ import annotations

import re
from pathlib import Path
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


def _bullets(batch: dict[str, Any] | None) -> list[str]:
    """Every distinct question the trained batch contained, in order."""
    if not batch:
        return []
    lines: list[str] = []
    for item in batch.get("items") or []:
        text = " ".join(str(item.get("query") or "").split())
        if text and text not in lines:
            lines.append(text)
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
    public = _public_metrics(body.get("metrics") or {})
    if public:
        updates["train_metrics"] = public
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
        metrics = _cycle_metrics(batch)
        cycles.append(
            {
                "id": str(batch.get("_id") or ""),
                "version": batch.get("model_version") or "",
                "date": _stamp(batch),
                "signals": len(batch.get("items") or []),
                "status": batch.get("job_status") or "submitted",
                "loss": metrics.get("loss"),
                "rank": metrics.get("rank"),
                "epochs": metrics.get("epochs"),
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
        live = _cycle_metrics(running)
        job = {
            "id": running.get("job_id") or "",
            "status": running.get("job_status") or "submitted",
            "phase": running.get("job_phase") or running.get("job_status") or "submitted",
            "model_version": running.get("model_version") or "",
            "metrics": live,
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


def _public_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """The numbers the Learning page shows for one run."""
    if not metrics:
        return {}
    epoch = metrics.get("epoch")
    if epoch is None:
        epoch = metrics.get("epochs")
    loss = metrics.get("final_loss")
    if loss is None:
        loss = metrics.get("loss")
    rank = metrics.get("lora_rank")
    if rank is None:
        rank = metrics.get("rank")
    if epoch is None and loss is None and rank is None:
        return {}
    return {
        "epoch": epoch,
        "epochs": metrics.get("epochs") if metrics.get("epochs") is not None else epoch,
        "loss": loss,
        "rank": rank,
        "max_epochs": metrics.get("max_epochs"),
    }


def _cycle_metrics(batch: dict[str, Any]) -> dict[str, Any]:
    stored = _public_metrics(batch.get("train_metrics") or {})
    if stored.get("loss") is not None or stored.get("epochs") is not None:
        return stored
    return _metrics_from_log(str(batch.get("job_id") or ""))


def _metrics_from_log(job_id: str) -> dict[str, Any]:
    if not job_id:
        return {}
    settings = get_settings()
    directory = Path(settings.BATCH_EXPORT_DIR).parent / "training_logs"
    path = directory / f"{job_id}.md"
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    return _parse_training_log(text)


def _parse_training_log(text: str) -> dict[str, Any]:
    """Read rank from the hyperparams section and the last pass from Metrics."""
    hyper = ""
    metrics = ""
    if "## Hyperparams" in text:
        hyper = text.split("## Hyperparams", 1)[1].split("##", 1)[0]
    if "## Metrics" in text:
        metrics = text.split("## Metrics", 1)[1]
    rank = _logged_number(hyper, "lora_rank")
    epochs = _logged_number(metrics, "epochs")
    loss = _logged_number(metrics, "final_loss")
    if epochs is None and loss is None and rank is None:
        return {}
    return {"epoch": epochs, "epochs": epochs, "loss": loss, "rank": rank, "max_epochs": None}


def _logged_number(section: str, name: str) -> float | None:
    match = re.search(rf"^- {re.escape(name)}:\s*([0-9.]+)\s*$", section, re.MULTILINE)
    if not match:
        return None
    return float(match.group(1))
