# Diagrams — Fine-Tune Service

## finetune-architecture.drawio

Components and **arrow direction**:

- **Manual trigger** → HTTP POST `/train` → Fine-Tune FastAPI :8004 (does not skip the app)
- FastAPI → `POST /train`, `GET /health`, `GET /status/:job_id`
- **ETL triples** `data/triples/{user_id}/` → `convert_triples()` (JSONL in)
- POST `/train` → convert → **LoRA worker** (PEFT / ms-swift / Unsloth)
- POST `/train` → **job store** (save job)
- GET `/status/:job_id` → job store (poll)
- LoRA worker → job store (status updates)
- LoRA worker → training log Markdown
- LoRA worker → **adapter files** `data/models/{user_id}/adapter/`
- Adapter --dashed--> **Frame 10** (merge + Q4, Premium on-device)

There is **no** arrow from the adapter into **LLM Service :8003**. The red box is intentional: cloud stays base. There is **no** AWS Bedrock.

## finetune-dataflow.drawio

1. **Submit**: Manual → POST `/train` → dataset exists? yes → convert → enqueue → 202. no → 404.
2. **Background LoRA**: `in_progress` → PEFT worker → save adapter + log → `completed`. Failure → `failed`. Completed --dashed--> Frame 10 only.
3. **Poll**: Client → GET `/status/:job_id` → job store → 200, or 404 if unknown.

Solid arrows = call / write. Dashed = HTTP 202 return, poll response, or future on-device build.

FastAPI also routes to `GET /status/:job_id` (architecture diagram). There is still no arrow from the adapter into LLM Service :8003.
