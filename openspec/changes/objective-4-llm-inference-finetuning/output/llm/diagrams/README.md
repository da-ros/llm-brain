# Diagrams — LLM Service

## llm-architecture.drawio

Components and **arrow direction**:

- **API Router :8000** (blue) → HTTP POST `/generate` and `/chat` → **FastAPI :8003**
- **ETL Service :8001** (blue) → HTTP POST `/extract` → **FastAPI :8003** (does not skip the app)
- FastAPI → `/generate`, `/chat`, `/health`, `/extract`
- `/generate` and `/chat` → **LLMProvider Protocol**
- Protocol --implements--> **QwenLocalProvider** (dashed)
- `/extract` → QwenLocalProvider
- QwenLocalProvider → **Qwen3.5-4B in-process weights** (local container, base, not fine-tuned)

There is **no** AWS Bedrock cloud, **no** Llama, and **no** arrow from Fine-Tune / LoRA adapter into this container. Frame 10 on-device is shown dashed and disconnected from inference.

## llm-dataflow.drawio

1. **Web inference**: Client → API Router → POST `/generate` → `get_provider(free or premium)` → `QwenLocalProvider.complete` → the same base Qwen3.5-4B runtime. Web free carries no RAG context. Dashed arrows return `{response, tokens_used}` to the API Router and then to the client. Phone free never takes this path.
2. **ETL extraction**: ETL → POST `/extract` → base Qwen reasons → JSON triples back to ETL (dashed).
3. **Errors**: missing prompt 400, unknown tier 400, container/model 500, timeout 504.

Solid arrows = call direction (left → right). Dashed = response.
