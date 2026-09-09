"""Task status polling — GET /tasks/:correlation_id."""

from typing import Annotated

import db
from auth import verify_token
from fastapi import APIRouter, Depends, HTTPException, Request, status
from logging_setup import log_with_correlation
from rate_limit import rate_limit_tasks

router = APIRouter(tags=["tasks"])


@router.get("/tasks/{correlation_id}")
async def get_task_status(
    request: Request,
    correlation_id: str,
    user: Annotated[dict, Depends(verify_token)],
    _: Annotated[dict, Depends(rate_limit_tasks)],
):
    """Return task_status for the caller's own correlation ID."""
    request_cid = getattr(request.state, "correlation_id", correlation_id)
    log_with_correlation(request_cid, "info", f"Polling task status: {correlation_id}")

    task = await db.find_task(correlation_id)
    if not task:
        log_with_correlation(correlation_id, "warning", "Task not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task not found: {correlation_id}",
        )

    if task.get("user_id") != user["user_id"]:
        log_with_correlation(correlation_id, "warning", "Access denied — wrong user")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this task",
        )

    log_with_correlation(
        correlation_id,
        "info",
        f"Task status: {task.get('status')} (retries={task.get('retries', 0)})",
    )

    return {
        "correlation_id": task["_id"],
        "status": task["status"],
        "retries": task.get("retries", 0),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
        "http_code": task.get("http_code"),
        "error_message": task.get("error_message"),
        "result": task.get("result"),
    }
