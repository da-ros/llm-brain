## Tasks

### A. LLM Service — Foundation

- [ ] A.1 Create `services/llm/__init__.py` — package init
- [ ] A.2 Create `services/llm/main.py` — FastAPI app with health endpoint
      — Correlation ID middleware, structured logging
- [ ] A.3 Create `services/llm/config.py` — pydantic-settings
      — AWS credentials, Bedrock model ID, service host/port
- [ ] A.4 Create `services/llm/Dockerfile` — container setup
- [ ] A.5 Create `services/llm/requirements.txt` — boto3, fastapi, pydantic-settings, uvicorn

### B. LLM Service — Provider Layer (migrate from monolith)

- [ ] B.1 Create `services/llm/providers/__init__.py`
- [ ] B.2 Migrate `services/api/llm/base.py` → `services/llm/providers/base.py`
      — LLMProvider Protocol (chat, complete)
- [ ] B.3 Migrate `services/api/llm/bedrock.py` → `services/llm/providers/bedrock.py`
      — BedrockProvider (boto3, Llama 3 8B)
- [ ] B.4 Migrate `services/api/llm/resolver.py` → `services/llm/providers/resolver.py`
      — get_provider(tier) — select by subscription tier
- [ ] B.5 Update imports: `services.api.llm.*` → `services.llm.providers.*`

### C. LLM Service — Endpoints

- [ ] C.1 Implement POST `/generate` endpoint
      — Request: `{"prompt": "...", "user_id": "..."}`
      — Response: `{"response": "...", "tokens_used": N}`
- [ ] C.2 Implement POST `/chat` endpoint
      — Request: `{"messages": [...], "context": "...", "user_id": "..."}`
      — Response: `{"response": "...", "tokens_used": N}`
- [ ] C.3 Add correlation ID propagation from request headers
- [ ] C.4 Add error handling: Bedrock throttling, model not found, timeout
- [ ] C.5 Add cost tracking: tokens used per request in response

### D. Fine-Tune Service — Foundation

- [ ] D.1 Create `services/finetune/__init__.py` — package init
- [ ] D.2 Create `services/finetune/main.py` — FastAPI app with health endpoint
      — Correlation ID middleware, structured logging
- [ ] D.3 Create `services/finetune/config.py` — pydantic-settings
      — AWS credentials, training hyperparams, service host/port
- [ ] D.4 Create `services/finetune/Dockerfile` — container setup
- [ ] D.5 Create `services/finetune/requirements.txt` — boto3, fastapi, pydantic-settings, uvicorn

### E. Fine-Tune Service — Training Pipeline

- [ ] E.1 Implement dataset preparation: triples (JSONL) → Bedrock training format
- [ ] E.2 Implement LoRA fine-tuning job submission to AWS Bedrock
- [ ] E.3 Implement training status polling (Bedrock API)
- [ ] E.4 Implement training completion handling (save LoRA adapter, update model version)

### F. Fine-Tune Service — Endpoints

- [ ] F.1 Implement POST `/train` endpoint
      — Request: `{"user_id": "...", "dataset_path": "..."}`
      — Response: `{"job_id": "...", "status": "submitted"}`
- [ ] F.2 Implement GET `/status/:job_id` endpoint
      — Response: `{"job_id": "...", "status": "...", "metrics": {...}}`
- [ ] F.3 Add correlation ID propagation
- [ ] F.4 Add training log: dataset info, hyperparams, metrics, model version

### G. Testing

- [ ] G.1 Unit tests for LLMProvider protocol (mock Bedrock)
- [ ] G.2 Unit tests for provider resolver (tier switching)
- [ ] G.3 Integration test: LLM Service `/generate` (mocked Bedrock)
- [ ] G.4 Integration test: LLM Service `/chat` (mocked Bedrock)
- [ ] G.5 Unit tests for Fine-Tune Service training pipeline
- [ ] G.6 Integration test: Fine-Tune Service `/train` + `/status` (mocked Bedrock)

### H. Monolith Cleanup

- [ ] H.1 Verify all LLM functionality works in `services/llm/`
- [ ] H.2 Verify API Router integrates with `services/llm/` (port 8003)
- [ ] H.3 Delete `services/api/` monolith
- [ ] H.4 Update `pyproject.toml` testpaths (remove services/api)
- [ ] H.5 Update memory files (project-architecture-overview.md)

### I. Documentation (output/)

- [ ] I.1 Create `output/documents/justificacion-ejemplo.md`
      — Component explanations, design patterns, SOLID principles, log examples
- [ ] I.2 Create `output/diagrams/llm-architecture.drawio`
      — LLM Service + Fine-Tune Service architecture
- [ ] I.3 Create `output/diagrams/llm-dataflow.drawio`
      — Request flow: API Router → LLM Service → Bedrock → Response
