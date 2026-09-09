# Diagrams — LLM Service

## llm-architecture.drawio

Architecture diagram showing:
- **API Router** (blue, existing) — upstream caller on port 8000
- **LLM Service** (green, new) — FastAPI app on port 8003
  - `POST /generate` — text completion
  - `POST /chat` — multimodal chat (text/image/video)
  - `GET /health` — provider status
  - Provider layer: LLMProvider Protocol → QwenLocalProvider → local Qwen3.5-4B container
- **Qwen3.5-4B (local Docker container, "cloud")** — multimodal inference (**base**, full precision, not fine-tuned)
- **Config** — Qwen model ID (LoRA adapter is for Premium on-device build, not this container)

**Color convention**:
- Blue: Existing components from previous frames
- Green: New components in this frame
- Orange: Local Qwen3.5-4B container ("cloud" = local container)

## llm-dataflow.drawio

Data flow diagram showing:
1. **Inference flow**: Client → API Router → LLM Service → Resolver → QwenLocalProvider → local Qwen3.5-4B container → Response (ETL Frame 2 also calls the base model to extract triples)
2. **Error paths**: local container unavailable (500), invalid tier (400), model not found (500), timeout (504), missing prompt (400/422)
3. **Key design notes**: asyncio.to_thread, per-request provider, stubbed local Qwen3.5-4B, correlation ID propagation
