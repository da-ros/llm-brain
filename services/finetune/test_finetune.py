"""Tests for Fine-Tune Service — Config, Pipeline, Health, Endpoints."""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add services/finetune to Python path
sys.path.insert(0, str(Path(__file__).parent))

# Set env vars before any imports
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test-key")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test-secret")
os.environ.setdefault("AWS_REGION", "us-east-1")


# --- Config Tests ---


class TestConfig:
    """Tests for Fine-Tune service configuration."""

    def test_config_defaults(self):
        """Test that config has correct defaults."""
        from config import Settings

        s = Settings()
        assert s.FINETUNE_PORT == 8004
        assert s.TRAINING_MAX_EPOCHS == 3
        assert s.AWS_REGION == "us-east-1"


# --- Pipeline Tests ---


class TestPipeline:
    """Tests for training pipeline."""

    def test_convert_triples_to_training_format(self):
        """Test converting triples JSONL to training format."""
        import pipeline

        # Create temp JSONL file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            json.dump({"subject": "Ibuprofeno", "predicate": "trata", "object": "dolor"}, f)
            f.write("\n")
            json.dump({"subject": "Aspirina", "predicate": "reduce", "object": "fiebre"}, f)
            f.write("\n")
            triples_path = f.name

        try:
            examples = pipeline.convert_triples_to_training_format(triples_path)
            assert len(examples) == 2
            assert "input" in examples[0]
            assert "output" in examples[0]
            assert examples[0]["input"] == "Ibuprofeno trata"
            assert examples[0]["output"] == "dolor"
        finally:
            Path(triples_path).unlink()

    def test_submit_training_job(self):
        """Test submitting a training job."""
        import pipeline

        # Create temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            json.dump({"subject": "test", "predicate": "is", "object": "ok"}, f)
            f.write("\n")
            triples_path = f.name

        try:
            job_id = pipeline.submit_training_job("user1", triples_path, {})
            assert isinstance(job_id, str)
            assert job_id.startswith("ft-job-")

            job = pipeline.get_job_status(job_id)
            assert job is not None
            assert job.status == "submitted"
            assert job.user_id == "user1"
            assert job.triples_count == 1
        finally:
            Path(triples_path).unlink()

    def test_get_job_status(self):
        """Test getting job status."""
        import pipeline

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            json.dump({"subject": "a", "predicate": "b", "object": "c"}, f)
            f.write("\n")
            triples_path = f.name

        try:
            job_id = pipeline.submit_training_job("user1", triples_path, {})
            job = pipeline.get_job_status(job_id)
            assert job is not None
            assert job.job_id == job_id
        finally:
            Path(triples_path).unlink()

    def test_get_nonexistent_job(self):
        """Test getting status of nonexistent job."""
        import pipeline

        result = pipeline.get_job_status("nonexistent")
        assert result is None

    def test_cancel_submitted_job(self):
        """Test cancelling a submitted job."""
        import pipeline

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            json.dump({"subject": "x", "predicate": "y", "object": "z"}, f)
            f.write("\n")
            triples_path = f.name

        try:
            job_id = pipeline.submit_training_job("user1", triples_path, {})
            cancelled = pipeline.cancel_job(job_id)
            assert cancelled is not None
            assert cancelled.status == "cancelled"
        finally:
            Path(triples_path).unlink()


# --- Health Endpoint Tests ---


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_returns_200(self):
        """Test that /health returns 200 with status ok."""
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "finetune-service"


# --- Train Endpoint Tests ---


class TestTrainEndpoint:
    """Tests for POST /train endpoint."""

    def test_train_returns_202(self):
        """Test that /train returns 202 with job_id."""
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)

        # Create temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            json.dump({"subject": "test", "predicate": "is", "object": "ok"}, f)
            f.write("\n")
            triples_path = f.name

        try:
            response = client.post(
                "/train",
                json={"user_id": "u1", "triples_path": triples_path},
                headers={"X-Request-ID": "test-123"},
            )
            assert response.status_code == 202
            data = response.json()
            assert "job_id" in data
            assert data["status"] == "submitted"
        finally:
            Path(triples_path).unlink()

    def test_status_returns_job_info(self):
        """Test that /status returns job info."""
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)

        # Create temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            json.dump({"subject": "a", "predicate": "b", "object": "c"}, f)
            f.write("\n")
            triples_path = f.name

        try:
            # Submit job
            response = client.post(
                "/train",
                json={"user_id": "u1", "triples_path": triples_path},
                headers={"X-Request-ID": "test-123"},
            )
            assert response.status_code == 202
            job_id = response.json()["job_id"]

            # Get status
            response = client.get(
                f"/status/{job_id}",
                headers={"X-Request-ID": "test-123"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["job_id"] == job_id
            assert data["status"] == "submitted"
        finally:
            Path(triples_path).unlink()

    def test_status_nonexistent_returns_404(self):
        """Test that /status returns 404 for nonexistent job."""
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.get(
            "/status/fake-id",
            headers={"X-Request-ID": "test-123"},
        )
        assert response.status_code == 404