## Proposal: LLM Inference (local Qwen3.5-4B container) + Fine-Tuning Services

### Context

The platform needs two backend LLM services:
1. **LLM Service** (port 8003): Handles multimodal inference requests from the API Router for premium users using **Qwen3.5-4B** served in a **local Docker container** ("cloud" = local container).
2. **Fine-Tune Service** (port 8004): Handles **local** LoRA fine-tuning jobs (PEFT / ms-swift / Unsloth) over Qwen3.5-4B as a background worker.

Currently, the LLM provider code lives in the monolith (`services/api/llm/`). This frame
extracts it into dedicated microservices and adds the local fine-tuning pipeline.

> **Note**: On-device LLM is NOT part of this frame. It goes in Frame 10 (Mobile App):
> Free = Qwen3.5-4B **base** quantized; Premium = Qwen3.5-4B **fine-tuned** quantized —
> both via React Native / Neural Engine / Metal.

### Why

1. **Microservice separation**: The LLM provider logic must be an independent service so the API Router can call it via HTTP (`http://llm-service:8003/generate`).
2. **Scaling independence**: LLM inference and fine-tuning have different resource profiles — they scale separately.
3. **Thesis OE4**: Anteproyecto specifies the main LLM plus LoRA fine-tuning. Here it is realized as a single model, **Qwen3.5-4B** (dense, natively multimodal: text/image/video; 262K ctx; Apache 2.0), served locally for premium and fine-tuned locally with LoRA.
4. **Monolith removal**: The `services/api/` monolith will be eliminated once all functionality is distributed across microservices.

### Deliverables

**LLM Service (`services/llm/`)**
- FastAPI app with `/generate` and `/chat` endpoints (multimodal: text, image, video)
- `LLMProvider` Protocol (migrated from monolith)
- Local Qwen3.5-4B provider implementation (**base** model, full precision — **not** fine-tuned; Premium cloud only)
- Provider resolver: selects by subscription tier
- Health endpoint with provider status (local Qwen3.5-4B container)
- Correlation ID support
- Dockerfile + requirements.txt

**Fine-Tune Service (`services/finetune/`)**
- FastAPI app with `/train` and `/status/:job_id` endpoints
- **Local** LoRA training pipeline (triples → local LoRA over Qwen3.5-4B) with PEFT / ms-swift / Unsloth
- Training job management (submit, poll, complete)
- Training log (dataset, hyperparams, metrics, model version)
- Produces a LoRA adapter; the on-device build merges + quantizes (Q4) for the **Premium** React Native app only (cloud container stays base)
- Dockerfile + requirements.txt

### Non-Deliverables

- On-device LLM (Qwen3.5-4B quantized in React Native via Neural Engine / Metal) — Frame 10
- AWS Bedrock / ECS / API Gateway deployment — future work, out of scope
- Model training from scratch
- Custom model architectures
- Multi-model ensemble

### References

- Anteproyecto: Objetivo Específico 4 (LLM principal)
- Context: single model Qwen3.5-4B; LLM Service port 8003, Fine-Tune Service port 8004; local-only MVP
- Depends on: Frame 1.1 (API Router). Built **before** Frame 2 so ETL can call the base
  Qwen3.5-4B for triple extraction. Fine-tune **training** later consumes Frame 2 triples
  at runtime (data dependency, not a build dependency).
