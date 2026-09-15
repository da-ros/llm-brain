## Tasks

### A. LLM Service — Foundation

- [x] A.1 Create `services/llm/__init__.py` — package init
- [x] A.2 Create `services/llm/main.py` — FastAPI app with health endpoint
      — Correlation ID middleware, structured logging
- [x] A.3 Create `services/llm/config.py` — pydantic-settings
      — Qwen3.5-4B model ID, service host/port (cloud = base; LoRA adapter used for Premium on-device build only)
- [x] A.4 Create `services/llm/Dockerfile` — container setup
- [x] A.5 Create `services/llm/requirements.txt` — fastapi, pydantic-settings, uvicorn

### B. LLM Service — Provider Layer (migrate from monolith)

- [x] B.1 Create `services/llm/providers/__init__.py`
- [x] B.2 Migrate `services/api/llm/base.py` → `services/llm/providers/base.py`
      — LLMProvider Protocol (chat, complete)
- [x] B.3 Migrate `services/api/llm/*.py` → `services/llm/providers/qwen_local.py`
      — Local Qwen3.5-4B provider (contenedor local, base model full precision — not fine-tuned)
- [x] B.4 Migrate `services/api/llm/resolver.py` → `services/llm/providers/resolver.py`
      — get_provider(tier) — select by subscription tier
- [x] B.5 Update imports: `services.api.llm.*` → `services.llm.providers.*`

### C. LLM Service — Endpoints

- [x] C.1 Implement POST `/generate` endpoint
      — Request: `{"prompt": "...", "user_id": "..."}`
      — Response: `{"response": "...", "tokens_used": N}`
- [x] C.2 Implement POST `/chat` endpoint
      — Request: `{"messages": [...], "context": "...", "user_id": "..."}`
      — Response: `{"response": "...", "tokens_used": N}`
- [x] C.3 Add correlation ID propagation from request headers
- [x] C.4 Add error handling: local Qwen3.5-4B container unavailable, model not found, timeout
- [x] C.5 Add cost tracking: tokens used per request in response

### D. Fine-Tune Service — Foundation

- [x] D.1 Create `services/finetune/__init__.py` — package init
- [x] D.2 Create `services/finetune/main.py` — FastAPI app with health endpoint
      — Correlation ID middleware, structured logging
- [x] D.3 Create `services/finetune/config.py` — pydantic-settings
      — base model (Qwen3.5-4B), LoRA backend (PEFT/ms-swift/Unsloth), training hyperparams, service host/port
- [x] D.4 Create `services/finetune/Dockerfile` — container setup
- [x] D.5 Create `services/finetune/requirements.txt` — fastapi, pydantic-settings, uvicorn

### E. Fine-Tune Service — Training Pipeline

- [x] E.1 Implement dataset preparation: triples (JSONL) → local LoRA training format
- [x] E.2 Implement local LoRA fine-tuning job over Qwen3.5-4B (PEFT/ms-swift/Unsloth)
- [x] E.3 Implement training status polling (local job store)
- [x] E.4 Implement training completion handling (save local LoRA adapter, update model version)

### F. Fine-Tune Service — Endpoints

- [x] F.1 Implement POST `/train` endpoint
      — Request: `{"user_id": "...", "dataset_path": "..."}`
      — Response: `{"job_id": "...", "status": "submitted"}`
- [x] F.2 Implement GET `/status/:job_id` endpoint
      — Response: `{"job_id": "...", "status": "...", "metrics": {...}}`
- [x] F.3 Add correlation ID propagation
- [x] F.4 Add training log: dataset info, hyperparams, metrics, model version

### G. Testing

- [x] G.1 Unit tests for LLMProvider protocol (mock local Qwen provider)
- [x] G.2 Unit tests for provider resolver (tier switching)
- [x] G.3 Integration test: LLM Service `/generate` (mocked local Qwen3.5-4B)
- [x] G.4 Integration test: LLM Service `/chat` (mocked local Qwen3.5-4B)
- [x] G.5 Unit tests for Fine-Tune Service training pipeline
- [x] G.6 Integration test: Fine-Tune Service `/train` + `/status` (mocked local LoRA)

### H. Monolith Cleanup

- [x] H.1 Verify all LLM functionality works in `services/llm/`
- [x] H.2 Verify API Router integrates with `services/llm/` (port 8003)
- [x] H.3 Delete `services/api/` monolith
- [x] H.4 Update `pyproject.toml` testpaths (remove services/api)
- [x] H.5 Update memory files (project-architecture-overview.md)

### I. Documentation (output/)

- [x] I.1 Create `output/llm/diagrams/llm-architecture.drawio` — LLM Service architecture
- [x] I.2 Create `output/llm/diagrams/llm-dataflow.drawio` — LLM Service data flow
- [x] I.3 Create `output/llm/documents/justificacion-ejemplo.md` — LLM justification
- [x] I.4 Create `output/finetune/diagrams/finetune-architecture.drawio` — Fine-Tune architecture
- [x] I.5 Create `output/finetune/diagrams/finetune-dataflow.drawio` — Fine-Tune data flow
- [x] I.6 Create `output/finetune/documents/justificacion-ejemplo.md` — Fine-Tune justification
