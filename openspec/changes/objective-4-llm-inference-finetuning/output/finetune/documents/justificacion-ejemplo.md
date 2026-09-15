# Justificación — Fine-Tune Service (Frame 4)

El Fine-Tune Service corre **LoRA local** sobre **Qwen3.5-4B** en el puerto 8004.
El producto es un **adapter** para el build Premium on-device (Frame 10). El
contenedor LLM :8003 **permanece base**. No hay AWS Bedrock managed fine-tuning.

## El problema que resuelve

1. **Trigger manual** — `POST /train` (el API Router lo expondrá como
   `POST /api/finetune` en Frame 5). Sin request, no hay job.
2. **Dataset de triples** — JSONL de ETL (`data/triples/{user_id}/`) convertido a
   formato instrucción `{instruction, input, output}`.
3. **Job asíncrono** — 202 + `job_id`. Polling en `GET /status/:job_id`.
4. **Artefactos** — adapter en `data/models/{user_id}/adapter/` + log Markdown
   (dataset, hyperparams, metrics, `model_version`).

## Módulos (SRP)

| Módulo | Responsabilidad |
|--------|-----------------|
| `main.py` | App FastAPI, correlation ID, routers |
| `config.py` | `BASE_MODEL_ID`, `LORA_BACKEND`, epochs, lr, max hours |
| `logging_setup.py` | Correlation ID en cada línea |
| `pipeline.py` | Job store, submit, poll, cancel, training log |
| `lora.py` | Backends PEFT / ms-swift / Unsloth (`LORA_MOCK` en CI) |
| `routers/health.py` | `GET /health` + `active_jobs` |
| `routers/training.py` | `POST /train` (202), `GET /status/:job_id` |

## Pipeline

```
POST /train (manual)
  → dataset existe? no → 404
  → triples JSONL → LoRA examples
  → job status=submitted, thread worker
  → 202 {job_id, status}
worker:
  → in_progress
  → LoRA over Qwen3.5-4B
  → save adapter + Markdown log
  → completed {epochs, final_loss, training_time_hours, model_version, adapter_path}
```

## Logging estructurado

```
2026-08-31T10:00:00 [abc-123] INFO finetune-service: POST /train — dataset: data/triples/user-123/receta.jsonl
2026-08-31T10:00:00 [abc-123] INFO finetune-service: Job submitted: ft-job-abc-123
2026-08-31T10:00:01 [abc-123] INFO finetune-service: Starting local LoRA job over Qwen3.5-4B (peft)
2026-08-31T12:00:00 [abc-123] INFO finetune-service: Job ft-job-abc-123 completed — loss: 0.15
```

Dataset ausente:

```
2026-08-31T10:00:00 [def-456] ERROR finetune-service: Dataset not found: Dataset not found: /missing.jsonl
```

## Patrones

| Pattern | Where | Purpose |
|---------|-------|---------|
| Command | `TrainingJob` | Job encapsula una corrida LoRA |
| Repository | in-memory `jobs` | Submit / get / cancel |
| Strategy | `LORA_BACKEND` | peft / ms-swift / unsloth |
| Pipeline | convert → train → save adapter | ETL triples → artifact on-device |

## SOLID

| Principio | Aplicación |
|-----------|-----------|
| **S** | El servicio solo gestiona jobs LoRA |
| **O** | Nuevo backend LoRA en `lora.py` sin cambiar routers |
| **L** | Cualquier backend cumple `run_lora_training` |
| **I** | Solo `/train`, `/status`, `/health` |
| **D** | Routers → pipeline, no → PEFT concreto |

## Errores HTTP

| Caso | Código |
|------|--------|
| `dataset_path` / `user_id` faltante | 400 |
| Dataset inexistente | 404 |
| JSONL sin triples válidos | 400 |
| Job desconocido | 404 |
| Error de training | job `failed` + 500 si falla el submit |
