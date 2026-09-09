# Spec: Fine-Tune Service

## ADDED Requirements

### Requirement: Local LoRA fine-tuning over Qwen3.5-4B

The Fine-Tune Service SHALL run **local** LoRA fine-tuning (PEFT / ms-swift /
Unsloth) over **Qwen3.5-4B** on port 8004, executed on the laptop (or Colab
free). It SHALL NOT use AWS Bedrock managed fine-tuning and SHALL NOT fine-tune
Llama models. It SHALL produce a LoRA **adapter**; the on-device build then
**merges + quantizes (Q4)** the model for download into the **Premium** React Native
app only. The cloud container SHALL remain the **base** model (not fine-tuned).
Free-tier on-device SHALL continue using the base quantized model.

#### Scenario: Submit a local training job

- **GIVEN** an authenticated request with a valid `dataset_path`
- **WHEN** the client sends `POST /train` with `user_id` and `dataset_path`
- **THEN** the service starts a local LoRA job over Qwen3.5-4B and responds HTTP 202 with a `job_id` and `status: "submitted"`

#### Scenario: Missing dataset is rejected

- **GIVEN** a `POST /train` request whose `dataset_path` does not exist
- **WHEN** the service validates the dataset
- **THEN** it responds HTTP 404 (dataset not found) and does not start a job

### Requirement: Manual trigger only

Local LoRA training SHALL be triggered **manually** via `POST /api/finetune`
(forwarded to `POST /train`). The service SHALL NOT start training automatically.

#### Scenario: Training starts only on manual trigger

- **GIVEN** accumulated triples/batches ready for training
- **WHEN** no `POST /api/finetune` request has been made
- **THEN** the service does not start any training job

### Requirement: Consumes accumulated triples from ETL

The Fine-Tune Service SHALL consume the triples/batches accumulated by the ETL
Service (Frame 2) as the training dataset for LoRA over Qwen3.5-4B.

#### Scenario: Convert triples to training format

- **GIVEN** a dataset of triples (JSONL) produced by ETL
- **WHEN** a training job is submitted
- **THEN** the service converts the triples to the local LoRA training format before starting Qwen3.5-4B fine-tuning

### Requirement: Training status polling

The service SHALL expose `GET /status/:job_id` to poll the state of a local
training job.

#### Scenario: Poll a completed job

- **GIVEN** a previously submitted `job_id`
- **WHEN** the client sends `GET /status/:job_id` after training finishes
- **THEN** the service responds HTTP 200 with `status: "completed"`, training `metrics` (epochs, final_loss, training_time_hours), the model version, and the **local** adapter path

#### Scenario: Unknown job

- **GIVEN** a `job_id` that does not exist
- **WHEN** the client sends `GET /status/:job_id`
- **THEN** the service responds HTTP 404

### Requirement: Health endpoint

The `GET /health` endpoint SHALL remain public and report service status.

#### Scenario: Public health

- **GIVEN** the Fine-Tune Service is running
- **WHEN** a client sends `GET /health`
- **THEN** the service responds HTTP 200 with `service: "finetune-service"` and the number of active jobs

## Notes

### Port

8004

### Endpoints (technical reference)

#### POST /train

Inicia un job de fine-tuning LoRA **local** (PEFT / ms-swift / Unsloth) sobre Qwen3.5-4B.

**Request**:
```json
{
  "user_id": "user-123",
  "dataset_path": "data/triples/user-123/receta.jsonl"
}
```

**Response 202 Accepted**:
```json
{
  "job_id": "ft-job-abc-123",
  "status": "submitted",
  "message": "Training job submitted. Poll GET /status/ft-job-abc-123 for status."
}
```

**Errors**:
- 400: Invalid request (missing dataset_path)
- 404: Dataset not found
- 500: Local training error

#### GET /status/:job_id

**Response 200**:
```json
{
  "job_id": "ft-job-abc-123",
  "status": "completed",
  "created_at": "2026-08-31T10:00:00Z",
  "completed_at": "2026-08-31T12:00:00Z",
  "metrics": {
    "epochs": 5,
    "final_loss": 0.15,
    "training_time_hours": 1.8
  },
  "model_version": "qwen3.5-4b-lora-v1",
  "adapter_path": "data/models/user-123/adapter/"
}
```

**Status values**:
- `submitted` — Job enviado, esperando inicio
- `in_progress` — Training en curso
- `completed` — Training completado exitosamente
- `failed` — Training falló
- `cancelled` — Job cancelado

#### GET /health

**Response 200**:
```json
{
  "status": "ok",
  "service": "finetune-service",
  "active_jobs": 0,
  "version": "0.1.0"
}
```

### Configuration

| Variable | Default | Descripción |
|----------|---------|-------------|
| `BASE_MODEL_ID` | `qwen3.5-4b` | Modelo base para fine-tuning local |
| `LORA_BACKEND` | `peft` | Backend de LoRA local (peft / ms-swift / unsloth) |
| `TRAINING_EPOCHS` | `5` | LoRA training epochs |
| `TRAINING_LR` | `0.001` | Learning rate |
| `MAX_TRAINING_TIME_HOURS` | `2` | Max training time before timeout |
| `FINETUNE_HOST` | `0.0.0.0` | Bind host |
| `FINETUNE_PORT` | `8004` | Bind port |

### Dependencies

- LoRA local (PEFT / ms-swift / Unsloth) sobre Qwen3.5-4B — sin AWS Bedrock
- Triples from ETL service (Frame 2)

### Training Pipeline

```
1. Receive POST /train request (manual trigger via POST /api/finetune)
2. Validate dataset exists at dataset_path
3. Convert triples (JSONL) → local LoRA training format
4. Run local LoRA fine-tuning over Qwen3.5-4B (PEFT / ms-swift / Unsloth)
5. Poll status until completed/failed
6. On completion: save local LoRA adapter path, update model version
7. On-device build merges + quantizes (Q4) the model for the React Native app (Frame 10)
8. Return status via GET /status/:job_id
```

### Integration

- **Upstream**: Manual trigger (`POST /api/finetune`) or agent (Frame 5) via HTTP
- **Downstream**: local LoRA training over Qwen3.5-4B; produces adapter for the on-device React Native build
- **Input**: Triples from ETL service (Frame 2) at `data/triples/{user_id}/`

### Correlation ID

El servicio propaga el header `X-Request-ID` en logs estructurados:
```
2026-08-31T10:00:00 [abc-123] INFO finetune-service: POST /train — dataset: data/triples/user-123/receta.jsonl
2026-08-31T10:00:01 [abc-123] INFO finetune-service: Starting local LoRA job over Qwen3.5-4B
2026-08-31T10:00:02 [abc-123] INFO finetune-service: Job submitted: ft-job-abc-123
2026-08-31T12:00:00 [abc-123] INFO finetune-service: Job ft-job-abc-123 completed — loss: 0.15
```
