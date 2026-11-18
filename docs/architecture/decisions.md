# Architecture decisions

Scope source of truth: `openspec/input/context.txt`. How the code runs today:
[current-runtime.md](current-runtime.md).

## In scope (local MVP)

- Single multimodal family: **Qwen3.5-4B**.
- Host inference is a process on port 8003 serving **base** Qwen3.5-4B.
  Web free and web premium share those weights. Premium chat adds RAG outside
  the model process. `QWEN_ADAPTER_PATH` is empty, so the LoRA adapter is not
  loaded there.
- On-device inference is `llama.rn` (llama.cpp, GGUF Q4_K_M, GPU via Metal).
  Free loads the base pack. Premium on-device loads that user's pack. The
  Neural Engine is not used.
- MongoDB and Chroma run as local Docker containers.
- Clients call the API Router directly. AWS API Gateway is future only.
- Fine-tune is a host process on port 8004. Compose builds `finetune-service`
  and does not publish that port. Callers use `host.docker.internal:8004`.
- Passwords are PBKDF2-HMAC-SHA256. Earlier frame text says bcrypt.

## What changed from the anteproyecto and the first sketch

| Topic | Earlier decision | Current implementation |
|-------|------------------|------------------------|
| LLM cloud | AWS Bedrock, Llama 3 8B, then a local container on port 8003 | Host process on port 8003. No LLM image. Containers call `host.docker.internal:8003` |
| On-device | llama.rn + Llama 3.2 3B, later described as Neural Engine / ExecuTorch / Core ML | Qwen3.5-4B GGUF Q4_K_M through `llama.rn` on the GPU (Metal) |
| Users | Anteproyecto "one user"; Frame 1 used an in-memory store in `apps/api` | Many accounts in MongoDB. The alpha adapter belongs to one account, Nora Vega |
| API layout | `apps/api` monolith | `services/api-router` on port 8000. The monolith is gone |
| Embeddings | MiniLM / Pinecone | Qwen3-VL-Embedding-2B, 2048 dimensions, in local Chroma |
| Analytics chart | Anteproyecto Chart.js | React scatter in `analytics-page.tsx` |
| Password hash | Frame 1 spec says bcrypt | PBKDF2-HMAC-SHA256, 200000 iterations, `salt$hash` |
| Retrieval depth | Thesis metric Precision@3 | The service retrieves `RAG_TOP_K` items, default 8. Precision@3 is computed on the first three |

## Provider resolution

`LLM_BACKEND` is `qwen_local` (`local` is an alias) or `ollama`. Any other
value fails at startup. `QWEN_MOCK=true` wins over both and returns the mock
provider. `LLM_PROVIDER` still appears in older env examples and in CI. The
resolver in `services/llm/providers/resolver.py` does not read it.

Web free and web premium both pass `get_provider`. The phone never does for
an on-device reply.

## Fine-tuning

Local LoRA writes `data/models/{user_id}/adapter/` and a Markdown log under
`data/training_logs/`. The host process on port 8003 stays the base model.
The premium phone pack is a separate Q4 GGUF produced from that adapter.

The alpha round uses `qwen3.5-4b-lora-v5`. Logs for versions 1 through 4 of
the same account remain in `thesis/evidence/finetune/`. September 2026 logs
for `user1` under pytest temporary paths are mock runs and are not part of
the round.
