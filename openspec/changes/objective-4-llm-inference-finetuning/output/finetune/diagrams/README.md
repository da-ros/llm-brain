# Diagrams — Fine-Tune Service

## finetune-architecture.drawio

Architecture diagram showing:
- **Agent / Manual trigger** (blue) — initiates training
- **Fine-Tune Service** (green, new) — FastAPI app on port 8004
  - `POST /train` (202 Accepted) — submit training job
  - `GET /status/:job_id` — poll training status
  - `GET /health` — service status
  - Training pipeline: convert_triples → submit_job → in-memory job store
- **Local LoRA over Qwen3.5-4B** (orange) — PEFT / ms-swift / Unsloth on the laptop; produces an adapter (merged + quantized Q4 for the React Native app)
- **Triples source** — data/triples/{user_id}/triples.jsonl from Frame 2
- **Config** — base model (Qwen3.5-4B), LoRA backend, training hyperparams

**Color convention**:
- Blue: Trigger (external)
- Green: New components in this frame
- Orange: Local LoRA training over Qwen3.5-4B

## finetune-dataflow.drawio

Data flow diagram showing:
1. **Submit flow**: Manual trigger (POST /api/finetune) → POST /train → Validate → Convert triples → Start local LoRA over Qwen3.5-4B → Save job → 202 Accepted
2. **Poll flow**: Trigger → GET /status/:job_id → Query job store → 200 OK
3. **Status values**: submitted → in_progress → completed/failed/cancelled
4. **Error paths**: Dataset not found (404), invalid dataset (400), job not found (404)
5. **Key design notes**: Async local training (hours), in-memory store, adapter merged + quantized for React Native, correlation ID, 202 pattern
