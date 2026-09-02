"""Training Router — Fine-tuning job submission and status.

Provides endpoints for:
- POST /train — Submit a LoRA training job
- GET /status/:job_id — Get training job status
"""

import pipeline

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

router = APIRouter(tags=["training"])


class TrainRequest(BaseModel):
    """Training request schema."""

    user_id: str
    triples_path: str
    config: dict = {}


class TrainResponse(BaseModel):
    """Training response schema."""

    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    """Job status response schema."""

    job_id: str
    status: str
    user_id: str
    created_at: str
    updated_at: str
    triples_count: int
    error: str | None = None
    metrics: dict = {}
    model_version: str | None = None
    adapter_path: str | None = None


@router.post("/train", response_model=TrainResponse, status_code=status.HTTP_202_ACCEPTED)
async def train(
    request: Request,
    body: TrainRequest,
):
    """Submit a LoRA training job.

    - **user_id**: User ID for the training
    - **triples_path**: Path to triples JSONL file
    - **config**: Optional training configuration overrides

    Returns 202 Accepted with job_id for polling.
    """
    from main import log_with_correlation

    correlation_id = getattr(request.state, "correlation_id", "no-id")

    log_with_correlation(
        correlation_id, "info",
        f"POST /train — dataset: {body.triples_path}, user_id: {body.user_id}",
    )

    try:
        job_id = pipeline.submit_training_job(
            user_id=body.user_id,
            triples_path=body.triples_path,
            config=body.config,
        )
    except FileNotFoundError as e:
        log_with_correlation(correlation_id, "error", f"Dataset not found: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ValueError as e:
        log_with_correlation(correlation_id, "error", f"Invalid dataset: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    log_with_correlation(
        correlation_id, "info",
        f"Job submitted: {job_id}",
    )

    return TrainResponse(
        job_id=job_id,
        status="submitted",
        message="Training job submitted",
    )


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_status(
    request: Request,
    job_id: str,
):
    """Get training job status.

    - **job_id**: The job ID to check
    """
    from main import log_with_correlation

    correlation_id = getattr(request.state, "correlation_id", "no-id")

    log_with_correlation(correlation_id, "info", f"GET /status/{job_id}")

    job = pipeline.get_job_status(job_id)

    if not job:
        log_with_correlation(correlation_id, "warning", f"Job not found: {job_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    log_with_correlation(
        correlation_id, "info",
        f"Job status: {job.status}",
    )

    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        user_id=job.user_id,
        created_at=job.created_at,
        updated_at=job.updated_at,
        triples_count=job.triples_count,
        error=job.error,
        metrics=job.metrics,
        model_version=job.model_version,
        adapter_path=job.adapter_path,
    )