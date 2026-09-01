# Diagrams — Fine-Tune Service

## finetune-architecture.drawio

Architecture diagram showing:
- **Agent / Manual trigger** (blue) — initiates training
- **Fine-Tune Service** (green, new) — FastAPI app on port 8004
  - `POST /train` (202 Accepted) — submit training job
  - `GET /status/:job_id` — poll training status
  - `GET /health` — service status
  - Training pipeline: convert_triples → submit_job → in-memory job store
- **AWS Bedrock** (orange, external) — LoRA fine-tuning on Llama 3 8B
- **Triples source** — data/triples/{user_id}/triples.jsonl from Frame 2
- **Config** — AWS credentials, training hyperparams

**Color convention**:
- Blue: Trigger (external)
- Green: New components in this frame
- Orange: External services (AWS Bedrock)

## finetune-dataflow.drawio

Data flow diagram showing:
1. **Submit flow**: Trigger → POST /train → Validate → Convert triples → Submit to Bedrock → Save job → 202 Accepted
2. **Poll flow**: Trigger → GET /status/:job_id → Query job store → 200 OK
3. **Status values**: submitted → in_progress → completed/failed/cancelled
4. **Error paths**: Dataset not found (404), invalid dataset (400), job not found (404)
5. **Key design notes**: Async training (hours), in-memory store, correlation ID, 202 pattern
