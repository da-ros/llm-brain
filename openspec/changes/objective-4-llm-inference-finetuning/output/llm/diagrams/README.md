# Diagrams — LLM Service

## llm-architecture.drawio

Components and **arrow direction**:

- **API Router :8000** (blue) → HTTP POST `/generate` and `/chat` → **FastAPI :8003**
- **ETL Service :8001** (blue) → HTTP POST `/extract` → **FastAPI :8003** (does not skip the app)
- FastAPI → `/generate`, `/chat`, `/health`, `/extract`
- `/generate` and `/chat` → **LLMProvider Protocol**
- Protocol --implements--> **QwenLocalProvider** (dashed) — backend `qwen_local` (Mac, torch/Metal)
- Protocol --implements--> **OllamaProvider** (dashed) — backend `ollama` (Linux/Windows, HTTP → Ollama)
- **resolver** — `LLM_BACKEND` elige el provider; `QWEN_MOCK=true` gana sobre cualquiera (default CI)
- `/extract` → provider resuelto (debe exponer `extract_triples`)
- QwenLocalProvider → **Qwen3.5-4B in-process weights** (host, base, not fine-tuned)
- OllamaProvider → **local Ollama server** (`OLLAMA_URL`, tag `OLLAMA_MODEL`)

There is **no** AWS Bedrock cloud, **no** Llama, and **no** arrow from Fine-Tune / LoRA adapter into this service. The service is a **host process** (not in Docker Compose). Frame 10 on-device is shown dashed and disconnected from inference.

## llm-dataflow.drawio

1. **Web inference**: Client → API Router → POST `/generate` → `get_provider(free or premium)` (valida tier + `LLM_BACKEND`, mock si `QWEN_MOCK=true`; el provider se cachea, no se crea por request) → `provider.complete` → the same base Qwen3.5-4B runtime. Web free carries no RAG context. Dashed arrows return `{response, tokens_used}` to the API Router and then to the client. Phone free never takes this path.
2. **ETL extraction**: ETL → POST `/extract` → base Qwen reasons → JSON triples back to ETL (dashed).
3. **Errors**: missing prompt 400, unknown tier 400, backend/model 500, timeout 504.

Solid arrows = call direction (left → right). Dashed = response.
