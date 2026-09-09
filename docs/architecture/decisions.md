# Architecture decisions — Frame 1

Scope source of truth: `openspec/input/context.txt`. This record lists where the
implemented foundation differs from earlier Bedrock/Atlas sketches.

## In scope (local MVP)

- Single multimodal family: **Qwen3.5-4B**.
- Cloud inference = **local Docker container** serving **base** Qwen3.5-4B (not fine-tuned) on port 8003.
- On-device: React Native on iPhone via Neural Engine / Metal — Free = base Q4; Premium = fine-tuned Q4.
- MongoDB and Chroma run as local Docker containers (not Atlas / Pinecone / Chroma Cloud).
- Clients call the API Router directly. AWS API Gateway is future only.

## Deviations from the first repo sketch

| Topic | Original sketch | This implementation |
|-------|-----------------|---------------------|
| LLM cloud | AWS Bedrock, Llama 3 8B | Local Qwen3.5-4B base container (`QwenLocalProvider`) |
| On-device | llama.rn + Llama 3.2 3B | Qwen3.5-4B Q4 in React Native / Neural Engine / Metal (`OnDeviceProvider`) |
| User store in Frame 1 | Implied Mongo from day one | In-memory store in `apps/api` so JWT tests run without Mongo. Later frames persist users in MongoDB. |
| API layout | `apps/api` only | Frame 1 foundation is `apps/api`. Frame 1.1 adds `services/api-router` (Kafka, correlation ID, upload/chat). Compose still starts `api-router` on port 8000 for the microservice stack; `apps/api` is the contract + Dockerfile `CMD`. |
| Embeddings | MiniLM / Pinecone | Qwen3-VL-Embedding-2B (2048-dim) in Chroma (later frames) |

## Provider resolution

`LLM_PROVIDER` is `ondevice` or `qwen_local` (`local` is an alias of `qwen_local` for CI).
Any other value (including `bedrock`) fails at startup.

## Fine-tuning

Local LoRA output is the **Premium on-device** build only. The cloud container stays base.
