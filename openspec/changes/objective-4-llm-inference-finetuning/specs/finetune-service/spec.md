# Spec: Fine-Tune Service

## Overview

Microservicio de fine-tuning LoRA en AWS Bedrock. Recibe datasets de triples
(extraídos por ETL en Frame 2) y ejecuta jobs de fine-tuning en background.

## Port

8004

## Endpoints

### POST /train

Envía un job de fine-tuning LoRA a AWS Bedrock.

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
- 500: Bedrock error

### GET /status/:job_id

Consulta el estado de un job de training.

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
  "model_version": "llama3-8b-lora-v1",
  "adapter_path": "s3://llm-brain/models/user-123/adapter/"
}
```

**Status values**:
- `submitted` — Job enviado, esperando inicio
- `in_progress` — Training en curso
- `completed` — Training completado exitosamente
- `failed` — Training falló
- `cancelled` — Job cancelado

**Errors**:
- 404: Job not found

### GET /health

Health check público.

**Response 200**:
```json
{
  "status": "ok",
  "service": "finetune-service",
  "active_jobs": 0,
  "version": "0.1.0"
}
```

## Configuration

| Variable | Default | Descripción |
|----------|---------|-------------|
| `AWS_ACCESS_KEY_ID` | — | AWS credential (required) |
| `AWS_SECRET_ACCESS_KEY` | — | AWS credential (required) |
| `AWS_REGION` | `us-east-1` | AWS region |
| `BEDROCK_MODEL_ID` | `meta.llama3-8b-instruct-v1:0` | Base model for fine-tuning |
| `TRAINING_EPOCHS` | `5` | LoRA training epochs |
| `TRAINING_LR` | `0.001` | Learning rate |
| `MAX_TRAINING_TIME_HOURS` | `2` | Max training time before timeout |
| `FINETUNE_HOST` | `0.0.0.0` | Bind host |
| `FINETUNE_PORT` | `8004` | Bind port |

## Dependencies

- AWS Bedrock (LoRA fine-tuning API)
- boto3 (AWS SDK)
- Triples from ETL service (Frame 2)

## Training Pipeline

```
1. Receive POST /train request
2. Validate dataset exists at dataset_path
3. Convert triples (JSONL) → Bedrock training format
4. Submit training job to AWS Bedrock
5. Poll status until completed/failed
6. On completion: save LoRA adapter path, update model version
7. Return status via GET /status/:job_id
```

## Integration

- **Upstream**: Manual trigger or agent (Frame 5) via HTTP
- **Downstream**: AWS Bedrock (LoRA training API)
- **Input**: Triples from ETL service (Frame 2) at `data/triples/{user_id}/`

## Correlation ID

El servicio propagа el header `X-Request-ID` en logs estructurados:
```
2026-08-31T10:00:00 [abc-123] INFO finetune-service: POST /train — dataset: data/triples/user-123/receta.jsonl
2026-08-31T10:00:01 [abc-123] INFO finetune-service: Submitting LoRA job to Bedrock
2026-08-31T10:00:02 [abc-123] INFO finetune-service: Job submitted: ft-job-abc-123
2026-08-31T12:00:00 [abc-123] INFO finetune-service: Job ft-job-abc-123 completed — loss: 0.15
```
