"""Evaluador nodes — heuristic score, weekly batch, manual Fine-Tune trigger."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from base import owned_or_404
from config import get_settings
from exceptions import LLMUpstreamError
from fastapi import HTTPException, status
from logging_setup import log_with_correlation
from tools import invoke_tool


async def evaluate_turn_node(state: dict[str, Any]) -> dict[str, Any]:
    """learn_graph evaluate node. Writes agent_feedback. Never POST /train."""
    correlation_id = state.get("correlation_id") or "no-id"
    log_with_correlation(correlation_id, "info", "learn_graph: evaluate_turn")
    result = await invoke_tool(
        "evaluate_turn",
        {
            "op": "score",
            "user_id": state.get("user_id") or "",
            "session_id": state.get("session_id") or "",
            "correlation_id": correlation_id,
            "query": state.get("query") or "",
            "response": state.get("response") or "",
            "assumptions": state.get("assumptions") or [],
        },
    )
    return {
        "score": float(result.get("score") or 0.0),
        "should_include_in_batch": bool(result.get("should_include_in_batch")),
    }


async def maybe_append_batch_node(state: dict[str, Any]) -> dict[str, Any]:
    """Append eligible turns to (user_id, ISO week). Status accumulating/ready."""
    correlation_id = state.get("correlation_id") or "no-id"
    if not state.get("should_include_in_batch"):
        log_with_correlation(
            correlation_id,
            "info",
            "learn_graph: maybe_append_batch skipped (below threshold)",
        )
        return {}
    log_with_correlation(correlation_id, "info", "learn_graph: maybe_append_batch")
    result = await invoke_tool(
        "evaluate_turn",
        {
            "op": "append_batch",
            "user_id": state.get("user_id") or "",
            "session_id": state.get("session_id") or "",
            "correlation_id": correlation_id,
            "query": state.get("query") or "",
            "response": state.get("response") or "",
            "assumptions": state.get("assumptions") or [],
        },
    )
    batch = result.get("batch") or {}
    return {"batch_status": batch.get("status")}


def export_batch_jsonl(batch: dict[str, Any]) -> str:
    """Write batch items as ETL-compatible triples JSONL for Fine-Tune."""
    settings = get_settings()
    user_id = batch["user_id"]
    iso_week = batch.get("iso_week") or "week"
    directory = Path(settings.BATCH_EXPORT_DIR) / user_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{iso_week}.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for item in batch.get("items") or []:
            row = {
                "subject": item.get("query") or "",
                "predicate": "was_answered",
                "object": item.get("response") or "",
                "metadata": {
                    "correlation_id": item.get("correlation_id"),
                    "session_id": item.get("session_id"),
                    "assumptions": item.get("assumptions") or [],
                    "user_id": user_id,
                    "iso_week": iso_week,
                },
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return str(path)


async def trigger_batch(
    *,
    batch_id: str,
    user_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Export JSONL and call finetune_trigger. 409 if not ready or empty."""
    import db

    log_with_correlation(
        correlation_id,
        "info",
        f"POST /batches/{batch_id}/trigger user_id={user_id}",
    )
    batch = owned_or_404(await db.find_batch(batch_id), user_id)
    items = batch.get("items") or []
    if batch.get("status") == "submitted":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Batch already submitted",
        )
    if batch.get("status") != "ready" or not items:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Batch is empty or not ready",
        )

    dataset_path = export_batch_jsonl(batch)
    try:
        result = await invoke_tool(
            "finetune_trigger",
            {
                "user_id": user_id,
                "dataset_path": dataset_path,
                "correlation_id": correlation_id,
            },
        )
    except LLMUpstreamError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    job_id = result.get("job_id") or ""
    updated = await db.update_batch(
        batch_id,
        {"status": "submitted", "dataset_path": dataset_path, "job_id": job_id},
        user_id=user_id,
    )
    log_with_correlation(
        correlation_id,
        "info",
        f"Batch {batch_id} submitted job_id={job_id} dataset={dataset_path}",
    )
    return {
        "job_id": job_id,
        "status": "submitted",
        "dataset_path": dataset_path,
        "batch": updated or batch,
    }


async def finalize_session(
    *,
    user_id: str,
    session_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Record session-end feedback. Does not call Fine-Tune POST /train."""
    import db

    log_with_correlation(
        correlation_id,
        "info",
        f"Evaluador finalize session_id={session_id} (no POST /train)",
    )
    feedback = await db.upsert_feedback(
        {
            "user_id": user_id,
            "correlation_id": f"session-end:{session_id}:{correlation_id}",
            "session_id": session_id,
            "score": 0.0,
            "reason": "session_ended",
            "should_include_in_batch": False,
        }
    )
    return {"feedback": feedback, "session_id": session_id}
