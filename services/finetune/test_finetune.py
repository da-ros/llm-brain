"""Tests for Fine-Tune Service — local LoRA pipeline, health, endpoints."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

os.environ["LORA_MOCK"] = "true"
os.environ["LORA_MOCK_DELAY_SECONDS"] = "0.05"
os.environ["BASE_MODEL_ID"] = "qwen3.5-4b"
os.environ["LORA_BACKEND"] = "peft"
os.environ["TRAINING_EPOCHS"] = "5"
os.environ["TRAINING_LR"] = "0.001"


def _write_triples(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


@pytest.fixture(autouse=True)
def _reset_jobs(tmp_path, monkeypatch):
    import pipeline
    from config import clear_settings_cache, get_settings

    monkeypatch.setenv("ADAPTER_OUTPUT_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("TRAINING_LOG_DIR", str(tmp_path / "logs"))
    clear_settings_cache()
    get_settings()
    pipeline.reset_jobs()
    yield
    pipeline.reset_jobs()
    clear_settings_cache()


class TestConfig:
    def test_config_defaults(self):
        from config import Settings

        s = Settings()
        assert s.FINETUNE_PORT == 8004
        assert s.BASE_MODEL_ID == "qwen3.5-4b"
        assert s.LORA_BACKEND == "peft"
        assert s.TRAINING_EPOCHS == 5
        assert s.LORA_RANK == 16
        assert s.TRAIN_LOSS_TARGET == 0.05
        assert s.TRAIN_MAX_EPOCHS == 30
        assert s.TRAINING_LR == 0.001
        assert s.MAX_TRAINING_TIME_HOURS == 2


class TestPipeline:
    """G.5 — triples → LoRA format, job store, adapter on completion."""

    def test_convert_triples_to_lora_format(self, tmp_path):
        import pipeline

        triples_path = tmp_path / "receta.jsonl"
        _write_triples(
            triples_path,
            [
                {"subject": "Ibuprofeno", "predicate": "trata", "object": "dolor"},
                {"subject": "Aspirina", "predicate": "reduce", "object": "fiebre"},
            ],
        )
        examples = pipeline.convert_triples_to_training_format(str(triples_path))
        assert len(examples) == 2
        assert examples[0]["input"] == "Ibuprofeno trata"
        assert examples[0]["output"] == "dolor"
        assert "instruction" in examples[0]

    def test_a_chat_fact_trains_as_a_question(self, tmp_path):
        import pipeline

        triples_path = tmp_path / "facts.jsonl"
        _write_triples(
            triples_path,
            [
                {
                    "subject": "Who is Theo Park?",
                    "predicate": "was_answered",
                    "object": "Theo Park is the engineer.",
                }
            ],
        )
        examples = pipeline.convert_triples_to_training_format(str(triples_path))
        assert len(examples) == 1
        assert examples[0]["input"] == "Who is Theo Park?"
        assert examples[0]["output"] == "Theo Park is the engineer."
        assert examples[0]["instruction"] == (
            "When the question is about this person's record, answer with that fact. "
            "For any other question, answer normally."
        )

    def test_chat_prompt_leaves_thinking_open(self):
        from lora import THINK_CLOSE, chat_prompt, trained_reply

        instruction = (
            "When the question is about this person's record, answer with that fact. "
            "For any other question, answer normally."
        )
        text = chat_prompt(instruction, "Who is Theo Park?")
        assert text == (
            "<|im_start|>system\n"
            f"{instruction}<|im_end|>\n"
            "<|im_start|>user\n"
            "Who is Theo Park?<|im_end|>\n"
            "<|im_start|>assistant\n"
            "<think>\n"
        )
        assert trained_reply("Theo Park is the engineer.") == "Theo Park is the engineer.<|im_end|>"
        assert (text + THINK_CLOSE + trained_reply("Theo Park is the engineer.")).endswith(
            "<think>\n</think>\n\nTheo Park is the engineer.<|im_end|>"
        )

    def test_convert_directory_of_jsonl(self, tmp_path):
        import pipeline

        dataset_dir = tmp_path / "user-123"
        dataset_dir.mkdir()
        _write_triples(
            dataset_dir / "a.jsonl",
            [{"subject": "a", "predicate": "is", "object": "1"}],
        )
        _write_triples(
            dataset_dir / "b.jsonl",
            [{"subject": "b", "predicate": "is", "object": "2"}],
        )
        examples = pipeline.convert_triples_to_training_format(str(dataset_dir))
        assert len(examples) == 2

    def test_missing_dataset_raises(self):
        import pipeline

        with pytest.raises(FileNotFoundError):
            pipeline.convert_triples_to_training_format("/no/such/file.jsonl")

    def test_empty_dataset_raises(self, tmp_path):
        import pipeline

        empty = tmp_path / "empty.jsonl"
        empty.write_text("\n", encoding="utf-8")
        with pytest.raises(ValueError, match="No valid triples"):
            pipeline.convert_triples_to_training_format(str(empty))

    def test_submit_and_complete(self, tmp_path):
        import pipeline

        triples_path = tmp_path / "receta.jsonl"
        _write_triples(
            triples_path,
            [{"subject": "test", "predicate": "is", "object": "ok"}],
        )
        job_id = pipeline.submit_training_job("user1", str(triples_path), "cid-1")
        assert job_id.startswith("ft-job-")

        deadline = time.time() + 3
        job = pipeline.get_job_status(job_id)
        while job and job.status not in ("completed", "failed") and time.time() < deadline:
            time.sleep(0.05)
            job = pipeline.get_job_status(job_id)

        assert job is not None
        assert job.status == "completed"
        assert job.model_version == "qwen3.5-4b-lora-v1"
        assert job.adapter_path
        assert Path(job.adapter_path, "adapter_config.json").exists()
        assert job.metrics.get("epochs") == 5
        assert "final_loss" in job.metrics
        assert job.log_path and Path(job.log_path).exists()
        log_text = Path(job.log_path).read_text(encoding="utf-8")
        assert "Hyperparams" in log_text
        assert "peft" in log_text

    def test_model_version_continues_from_the_logs(self, tmp_path):
        import pipeline
        from config import get_settings

        log_dir = Path(get_settings().TRAINING_LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "ft-job-older.md").write_text(
            "- **model_version**: qwen3.5-4b-lora-v2\n",
            encoding="utf-8",
        )
        triples_path = tmp_path / "receta.jsonl"
        _write_triples(
            triples_path,
            [{"subject": "test", "predicate": "is", "object": "ok"}],
        )
        first = pipeline.submit_training_job("user1", str(triples_path), "cid-v")
        second = pipeline.submit_training_job("user1", str(triples_path), "cid-v2")
        deadline = time.time() + 3
        jobs = []
        while time.time() < deadline:
            jobs = [pipeline.get_job_status(first), pipeline.get_job_status(second)]
            if all(job and job.status in ("completed", "failed") for job in jobs):
                break
            time.sleep(0.05)
        versions = {job.model_version for job in jobs if job}
        assert versions == {"qwen3.5-4b-lora-v3", "qwen3.5-4b-lora-v4"}

    def test_get_nonexistent_job(self):
        import pipeline

        assert pipeline.get_job_status("nonexistent") is None

    def test_cancel_submitted_job(self, tmp_path, monkeypatch):
        import pipeline
        from config import clear_settings_cache as clear

        monkeypatch.setenv("LORA_MOCK_DELAY_SECONDS", "2")
        clear()
        triples_path = tmp_path / "slow.jsonl"
        _write_triples(
            triples_path,
            [{"subject": "x", "predicate": "y", "object": "z"}],
        )
        job_id = pipeline.submit_training_job("user1", str(triples_path))
        cancelled = pipeline.cancel_job(job_id)
        assert cancelled is not None
        assert cancelled.status == "cancelled"


class TestHealthEndpoint:
    def test_health_returns_200(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "finetune-service"
        assert "active_jobs" in data


class TestTrainEndpoint:
    """G.6 — POST /train + GET /status with mocked local LoRA."""

    def test_train_returns_202_and_completes(self, tmp_path):
        from fastapi.testclient import TestClient
        from main import app

        triples_path = tmp_path / "receta.jsonl"
        _write_triples(
            triples_path,
            [{"subject": "Ibuprofeno", "predicate": "trata", "object": "dolor"}],
        )
        client = TestClient(app)
        response = client.post(
            "/train",
            json={"user_id": "user-123", "dataset_path": str(triples_path)},
            headers={"X-Request-ID": "abc-123"},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "submitted"
        assert data["job_id"].startswith("ft-job-")
        assert "Poll GET /status/" in data["message"]
        assert response.headers.get("X-Request-ID") == "abc-123"

        job_id = data["job_id"]
        deadline = time.time() + 3
        status_data = {}
        while time.time() < deadline:
            status_response = client.get(f"/status/{job_id}", headers={"X-Request-ID": "abc-123"})
            assert status_response.status_code == 200
            status_data = status_response.json()
            if status_data["status"] == "completed":
                break
            time.sleep(0.05)

        assert status_data["status"] == "completed"
        assert status_data["phase"] == "completed"
        assert status_data["metrics"]["epochs"] == 5
        assert status_data["model_version"]
        assert status_data["adapter_path"]
        assert status_data["completed_at"]

    def test_dataset_not_found_returns_404(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post(
            "/train",
            json={"user_id": "u1", "dataset_path": "/no/such/receta.jsonl"},
        )
        assert response.status_code == 404

    def test_missing_dataset_path_returns_400(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post("/train", json={"user_id": "u1"})
        assert response.status_code == 400

    def test_publish_requires_an_adapter(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.post("/publish", json={"user_id": "user-a"})
        assert response.status_code == 404

    def test_publish_rejects_a_second_pack(self, monkeypatch):
        from fastapi.testclient import TestClient
        from config import get_settings
        from main import app

        adapter = Path(get_settings().ADAPTER_OUTPUT_DIR) / "user-a" / "adapter"
        adapter.mkdir(parents=True)
        (adapter / "adapter_config.json").write_text("{}", encoding="utf-8")

        def already(*_args, **_kwargs):
            raise RuntimeError("A pack is already being published.")

        monkeypatch.setattr("publish_pack.start_publish", already)
        client = TestClient(app)
        response = client.post("/publish", json={"user_id": "user-a"})
        assert response.status_code == 409

    def test_status_unknown_returns_404(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        response = client.get("/status/fake-id")
        assert response.status_code == 404
