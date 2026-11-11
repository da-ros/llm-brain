"""Training pipeline — triples JSONL → local LoRA over Qwen3.5-4B.

Jobs run in a background thread. On completion the adapter is saved locally
for the Premium on-device build; the cloud LLM container stays base.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from config import get_settings
from logging_setup import log_with_correlation, logger
from lora import TrainingMetrics, run_lora_training

jobs: dict[str, TrainingJob] = {}
_jobs_lock = threading.Lock()
_version_lock = threading.Lock()
_model_version_seq = 0


@dataclass
class TrainingJob:
    """Represents a local LoRA training job."""

    job_id: str
    status: str
    user_id: str
    dataset_path: str
    created_at: str
    updated_at: str
    triples_count: int
    hyperparams: dict
    correlation_id: str = "no-id"
    phase: str = "submitted"
    error: str | None = None
    metrics: dict = field(default_factory=dict)
    model_version: str | None = None
    adapter_path: str | None = None
    log_path: str | None = None
    completed_at: str | None = None


def reset_jobs() -> None:
    """Clear the in-memory job store (tests)."""
    with _jobs_lock:
        jobs.clear()


def get_active_jobs_count() -> int:
    """Count jobs that are submitted or in progress."""
    with _jobs_lock:
        return sum(1 for job in jobs.values() if job.status in ("submitted", "in_progress"))


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _next_model_version(base_model_id: str) -> str:
    global _model_version_seq
    with _version_lock:
        _model_version_seq += 1
        return f"{base_model_id}-lora-v{_model_version_seq}"


def _jsonl_files(dataset_path: str) -> list[Path]:
    path = Path(_host_dataset_path(dataset_path))
    if path.is_file():
        return [path]
    if path.is_dir():
        files = sorted(path.glob("*.jsonl"))
        if files:
            return files
    raise FileNotFoundError(f"Dataset not found: {dataset_path}")


def _host_dataset_path(dataset_path: str) -> str:
    """Agents write /app/data inside the container. The host copy is ./data."""
    path = Path(dataset_path)
    if path.exists():
        return str(path)
    marker = "/app/data/"
    if dataset_path.startswith(marker):
        local = Path(__file__).resolve().parents[2] / "data" / dataset_path[len(marker) :]
        if local.exists():
            return str(local)
    return dataset_path


def convert_triples_to_training_format(dataset_path: str) -> list[dict]:
    """Convert ETL triples JSONL into local LoRA instruction examples.

    Input (ETL):
        {"subject": "...", "predicate": "...", "object": "...", "metadata": {...}}

    Output (PEFT / ms-swift / Unsloth instruction format):
        {"instruction": "...", "input": "subject predicate", "output": "object"}
    """
    examples: list[dict] = []
    for file_path in _jsonl_files(dataset_path):
        with file_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    triple = json.loads(line)
                except json.JSONDecodeError:
                    continue
                subject = triple.get("subject")
                predicate = triple.get("predicate")
                obj = triple.get("object")
                if not subject or not predicate or not obj:
                    continue
                if predicate == "was_answered":
                    examples.append(
                        {
                            "instruction": (
                                "Answer from this person's own record. "
                                "Use only the facts that record states."
                            ),
                            "input": str(subject),
                            "output": str(obj),
                            "metadata": triple.get("metadata") or {},
                        }
                    )
                    continue
                examples.append(
                    {
                        "instruction": (
                            "Complete the personal knowledge triple. "
                            "Given subject and predicate, produce the object."
                        ),
                        "input": f"{subject} {predicate}",
                        "output": str(obj),
                        "metadata": triple.get("metadata") or {},
                    }
                )
    if not examples:
        raise ValueError(f"No valid triples found in {dataset_path}")
    return examples


def write_training_log(job: TrainingJob, metrics: TrainingMetrics | None = None) -> str:
    """Write a Markdown experiment log (dataset, hyperparams, metrics, version)."""
    settings = get_settings()
    log_dir = Path(settings.TRAINING_LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{job.job_id}.md"
    lines = [
        f"# Fine-tune job `{job.job_id}`",
        "",
        f"- **user_id**: {job.user_id}",
        f"- **dataset_path**: `{job.dataset_path}`",
        f"- **triples_count**: {job.triples_count}",
        f"- **status**: {job.status}",
        f"- **created_at**: {job.created_at}",
        f"- **completed_at**: {job.completed_at or ''}",
        f"- **model_version**: {job.model_version or ''}",
        f"- **adapter_path**: `{job.adapter_path or ''}`",
        "",
        "## Hyperparams",
        "",
        f"- backend: `{job.hyperparams.get('backend')}`",
        f"- base_model: `{job.hyperparams.get('base_model_id')}`",
        f"- epochs: {job.hyperparams.get('epochs')}",
        f"- learning_rate: {job.hyperparams.get('learning_rate')}",
        f"- max_training_time_hours: {job.hyperparams.get('max_training_time_hours')}",
        "",
    ]
    if metrics:
        lines.extend(
            [
                "## Metrics",
                "",
                f"- epochs: {metrics.epochs}",
                f"- final_loss: {metrics.final_loss}",
                f"- training_time_hours: {metrics.training_time_hours}",
                "",
            ]
        )
    if job.error:
        lines.extend(["## Error", "", job.error, ""])
    log_path.write_text("\n".join(lines), encoding="utf-8")
    return str(log_path)


def _run_job(job_id: str) -> None:
    settings = get_settings()
    with _jobs_lock:
        job = jobs.get(job_id)
        if job is None or job.status == "cancelled":
            return
        job.status = "in_progress"
        job.phase = "preparing"
        job.updated_at = _now()
        correlation_id = job.correlation_id
        dataset_path = job.dataset_path
        user_id = job.user_id

    log_with_correlation(
        correlation_id,
        "info",
        f"Starting local LoRA job over Qwen3.5-4B ({settings.LORA_BACKEND})",
    )

    try:
        examples = convert_triples_to_training_format(dataset_path)
        with _jobs_lock:
            job = jobs.get(job_id)
            if job is None or job.status == "cancelled":
                return
            job.phase = "training"
            job.updated_at = _now()
        adapter_dir = Path(settings.ADAPTER_OUTPUT_DIR) / user_id / "adapter"
        metrics = run_lora_training(
            examples=examples,
            adapter_dir=adapter_dir,
            settings=settings,
        )
        version = _next_model_version(settings.BASE_MODEL_ID)
        with _jobs_lock:
            job = jobs.get(job_id)
            if job is None:
                return
            if job.status == "cancelled":
                return
            job.status = "completed"
            job.phase = "completed"
            job.updated_at = _now()
            job.completed_at = job.updated_at
            job.adapter_path = str(adapter_dir)
            job.model_version = version
            job.metrics = {
                "epochs": metrics.epochs,
                "final_loss": metrics.final_loss,
                "training_time_hours": metrics.training_time_hours,
                "backend": metrics.backend,
            }
            job.log_path = write_training_log(job, metrics)
        log_with_correlation(
            correlation_id,
            "info",
            f"Job {job_id} completed — loss: {metrics.final_loss}",
        )
    except Exception as exc:
        logger.exception("LoRA job %s failed", job_id)
        with _jobs_lock:
            job = jobs.get(job_id)
            if job is None:
                return
            job.status = "failed"
            job.phase = "failed"
            job.updated_at = _now()
            job.completed_at = job.updated_at
            job.error = str(exc)
            job.log_path = write_training_log(job)
        log_with_correlation(correlation_id, "error", f"Job {job_id} failed: {exc}")


def submit_training_job(
    user_id: str,
    dataset_path: str,
    correlation_id: str = "no-id",
) -> str:
    """Validate the dataset, enqueue a local LoRA job, return job_id."""
    examples = convert_triples_to_training_format(dataset_path)
    settings = get_settings()
    job_id = f"ft-job-{uuid.uuid4().hex[:8]}"
    now = _now()
    job = TrainingJob(
        job_id=job_id,
        status="submitted",
        user_id=user_id,
        dataset_path=dataset_path,
        created_at=now,
        updated_at=now,
        triples_count=len(examples),
        hyperparams={
            "backend": settings.LORA_BACKEND,
            "base_model_id": settings.BASE_MODEL_ID,
            "epochs": settings.TRAINING_EPOCHS,
            "learning_rate": settings.TRAINING_LR,
            "max_training_time_hours": settings.MAX_TRAINING_TIME_HOURS,
        },
        correlation_id=correlation_id,
        log_path=None,
    )
    job.log_path = write_training_log(job)
    with _jobs_lock:
        jobs[job_id] = job

    log_with_correlation(correlation_id, "info", f"Job submitted: {job_id}")
    worker = threading.Thread(target=_run_job, args=(job_id,), daemon=True, name=f"lora-{job_id}")
    worker.start()
    return job_id


def get_job_status(job_id: str) -> TrainingJob | None:
    """Look up a training job."""
    with _jobs_lock:
        return jobs.get(job_id)


def cancel_job(job_id: str) -> TrainingJob | None:
    """Cancel a submitted or in-progress job."""
    with _jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return None
        if job.status in ("submitted", "in_progress"):
            job.status = "cancelled"
            job.updated_at = _now()
            job.completed_at = job.updated_at
            return job
        return None
