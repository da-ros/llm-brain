# Project architecture overview

Source of truth: `openspec/input/context.txt`. This file tracks the running
microservice map as frames land.

## Local MVP ("cloud" = Docker on the laptop)

| Service | Port | Role |
|---------|------|------|
| API Router | 8000 | JWT gateway, Kafka upload, sync chat |
| ETL | 8001 | One-tap distillation → triples JSONL |
| RAG | 8002 | Mongo + Chroma retrieval |
| **LLM Service** | **8003** | **Base** Qwen3.5-4B inference (Premium + ETL). Not fine-tuned. |
| **Fine-Tune Service** | **8004** | Local LoRA over Qwen3.5-4B. Manual `POST /train` only. |

Free-tier chat is on-device (Frame 10): base Qwen3.5-4B Q4 in React Native.
It never hits port 8003.

## Frame 4 (this change)

- Cloud LLM stays **base**. The LoRA adapter is written to
  `data/models/{user_id}/adapter/` for the **Premium on-device** build later.
  There is no runtime path from Fine-Tune into LLM Service :8003.
- API Router already calls `http://llm-service:8003/generate` with `X-Request-ID`.
- ETL (Frame 2) uses the same base model (`POST /extract`) for triples.
- AWS Bedrock / Llama are out of scope.

See also [decisions.md](decisions.md) and [stack.md](stack.md).
