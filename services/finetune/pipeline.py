"""Training Pipeline — LoRA fine-tuning on AWS Bedrock.

Handles:
- Converting triples JSONL to Bedrock training format
- Submitting training jobs to AWS Bedrock
- Tracking job status in-memory
"""

import json
import uuid
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# --- In-memory job store ---
jobs: dict[str, "TrainingJob"] = {}
_jobs_lock = threading.Lock()


@dataclass
class TrainingJob:
    """Represents a fine-tuning training job."""

    job_id: str
    status: str  # submitted, in_progress, completed, failed, cancelled
    user_id: str
    created_at: str
    updated_at: str
    triples_count: int
    config: dict
    error: str | None = None
    metrics: dict = field(default_factory=dict)
    model_version: str | None = None
    adapter_path: str | None = None


def get_active_jobs_count() -> int:
    """Get count of active (non-completed, non-failed) jobs."""
    with _jobs_lock:
        return sum(
            1 for job in jobs.values()
            if job.status in ("submitted", "in_progress")
        )


def convert_triples_to_training_format(triples_path: str) -> list[dict]:
    """Convert triples JSONL to Bedrock LoRA training format.

    Input format (from ETL service):
        {"subject": "...", "predicate": "...", "object": "...", "metadata": {...}}

    Output format (Bedrock training):
        {"input": "subject predicate", "output": "object"}

    Args:
        triples_path: Path to JSONL file with triples

    Returns:
        List of training examples

    Raises:
        FileNotFoundError: If the triples file doesn't exist
        ValueError: If the file is empty or invalid
    """
    path = Path(triples_path)
    if not path.exists():
        raise FileNotFoundError(f"Triples file not found: {triples_path}")

    training_examples = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                triple = json.loads(line)
                training_examples.append({
                    "input": f"{triple['subject']} {triple['predicate']}",
                    "output": triple["object"],
                })
            except (json.JSONDecodeError, KeyError):
                continue

    if not training_examples:
        raise ValueError(f"No valid triples found in {triples_path}")

    return training_examples


def submit_training_job(
    user_id: str,
    triples_path: str,
    config: dict,
) -> str:
    """Submit a LoRA training job.

    Args:
        user_id: User ID for the job
        triples_path: Path to triples JSONL file
        config: Training configuration overrides

    Returns:
        The job ID

    Raises:
        FileNotFoundError: If the triples file doesn't exist
        ValueError: If the file has no valid triples
    """
    # Validate dataset exists
    triples = convert_triples_to_training_format(triples_path)

    job_id = f"ft-job-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()

    job = TrainingJob(
        job_id=job_id,
        status="submitted",
        user_id=user_id,
        created_at=now,
        updated_at=now,
        triples_count=len(triples),
        config=config,
    )

    with _jobs_lock:
        jobs[job_id] = job

    return job_id


def get_job_status(job_id: str) -> TrainingJob | None:
    """Get the status of a training job.

    Args:
        job_id: The job ID to look up

    Returns:
        The TrainingJob if found, None otherwise
    """
    with _jobs_lock:
        return jobs.get(job_id)


def cancel_job(job_id: str) -> TrainingJob | None:
    """Cancel a training job.

    Args:
        job_id: The job ID to cancel

    Returns:
        The updated TrainingJob if found and cancellable, None otherwise
    """
    with _jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return None
        if job.status in ("submitted", "in_progress"):
            job.status = "cancelled"
            job.updated_at = datetime.now(timezone.utc).isoformat()
            return job
        return None