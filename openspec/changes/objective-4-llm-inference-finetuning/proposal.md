## Proposal: LLM Cloud (Bedrock) + Fine-Tuning Services

### Context

The platform needs two backend LLM services:
1. **LLM Service** (port 8003): Handles inference requests from the API Router for premium users via AWS Bedrock.
2. **Fine-Tune Service** (port 8004): Handles LoRA fine-tuning jobs on AWS Bedrock as a background worker.

Currently, the LLM provider code lives in the monolith (`services/api/llm/`). This frame
extracts it into dedicated microservices and adds the fine-tuning pipeline.

> **Note**: On-device LLM (llama.rn) is NOT part of this frame. It goes in Frame 10 (Mobile App).

### Why

1. **Microservice separation**: The LLM provider logic must be an independent service so the API Router can call it via HTTP (`http://llm-service:8003/generate`).
2. **Scaling independence**: LLM inference and fine-tuning have different resource profiles — they scale separately.
3. **Thesis OE4**: Anteproyecto specifies LoRA fine-tuning on AWS Bedrock (Llama 3 8B) and cloud inference for premium tier.
4. **Monolith removal**: The `services/api/` monolith will be eliminated once all functionality is distributed across microservices.

### Deliverables

**LLM Service (`services/llm/`)**
- FastAPI app with `/generate` and `/chat` endpoints
- `LLMProvider` Protocol (migrated from monolith)
- `BedrockProvider` implementation (migrated from monolith)
- Provider resolver: selects by subscription tier
- Health endpoint with provider status
- Correlation ID support
- Dockerfile + requirements.txt

**Fine-Tune Service (`services/finetune/`)**
- FastAPI app with `/train` and `/status/:job_id` endpoints
- LoRA training pipeline (triples → Bedrock training format)
- Training job management (submit, poll, complete)
- Training log (dataset, hyperparams, metrics, model version)
- Dockerfile + requirements.txt

### Non-Deliverables

- On-device LLM (llama.rn) — Frame 10
- Model training from scratch
- Custom model architectures
- Multi-model ensemble

### References

- Anteproyecto: Objetivo Específico 4 (LLM principal)
- Context: LLM Service port 8003, Fine-Tune Service port 8004
- Depends on: Frame 2 (Memory Distillation — provides triples for fine-tuning)
