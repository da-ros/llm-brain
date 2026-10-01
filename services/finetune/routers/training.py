"""Training router — POST /train and GET /status/:job_id."""

from __future__ import annotations

import pipeline
from fastapi import APIRouter, HTTPException, Request, status
from logging_setup import log_with_correlation
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["training"])


class TrainRequest(BaseModel):
    """Training request schema (spec: user_id + dataset_path)."""

    user_id: str | None = None
    dataset_path: str | None = None


class TrainResponse(BaseModel):
    """Training response schema."""

    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    """Job status response schema."""

    model_config = ConfigDict(protected_namespaces=())

    job_id: str
    status: str
    phase: str = "submitted"
    created_at: str
    completed_at: str | None = None
    metrics: dict = {}
    model_version: str | None = None
    adapter_path: str | None = None


@router.post("/train", response_model=TrainResponse, status_code=status.HTTP_202_ACCEPTED)
async def train(request: Request, body: TrainRequest):
    """Submit a local LoRA job. Training does not start automatically elsewhere."""
    correlation_id = getattr(request.state, "correlation_id", "no-id")

    if not body.dataset_path or not body.dataset_path.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request (missing dataset_path)",
        )
    if not body.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request (missing user_id)",
        )

    log_with_correlation(
        correlation_id,
        "info",
        f"POST /train — dataset: {body.dataset_path}",
    )

    try:
        job_id = pipeline.submit_training_job(
            user_id=body.user_id,
            dataset_path=body.dataset_path,
            correlation_id=correlation_id,
        )
    except FileNotFoundError as exc:
        log_with_correlation(correlation_id, "error", f"Dataset not found: {exc}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        log_with_correlation(correlation_id, "error", f"Invalid dataset: {exc}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        log_with_correlation(correlation_id, "error", f"Local training error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Local training error: {exc}",
        ) from exc

    return TrainResponse(
        job_id=job_id,
        status="submitted",
        message=f"Training job submitted. Poll GET /status/{job_id} for status.",
    )


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_status(request: Request, job_id: str):
    """Poll the state of a local LoRA job."""
    correlation_id = getattr(request.state, "correlation_id", "no-id")
    log_with_correlation(correlation_id, "info", f"GET /status/{job_id}")

    job = pipeline.get_job_status(job_id)
    if not job:
        log_with_correlation(correlation_id, "warning", f"Job not found: {job_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    log_with_correlation(correlation_id, "info", f"Job status: {job.status}")
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        phase=job.phase,
        created_at=job.created_at,
        completed_at=job.completed_at,
        metrics=job.metrics,
        model_version=job.model_version,
        adapter_path=job.adapter_path,
    )
