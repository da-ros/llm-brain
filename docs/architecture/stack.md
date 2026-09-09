# OSS stack — Frame 1

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Language | Python 3.13 | Async FastAPI, first-class typing, thesis runtime |
| API | FastAPI + uvicorn | Health, JWT dependencies, OpenAPI for the defense |
| Settings | pydantic-settings | `.env` + fail-fast validation |
| Auth | JWT (python-jose) + bcrypt | Multi-tenant `user_id` + `subscription_tier` |
| LLM protocol | `LLMProvider` Protocol | Switch on-device vs local container without rewriting callers |
| Cloud LLM | Qwen3.5-4B **base** in Docker :8003 | $0, local, multimodal; not Bedrock |
| On-device LLM | Qwen3.5-4B Q4, React Native / Neural Engine / Metal | Free = base; Premium = fine-tuned |
| Embeddings (later) | Qwen3-VL-Embedding-2B, 2048-dim | Same family, Matryoshka-truncatable |
| Documents | MongoDB 7 + GridFS (local) | Binaries + task_status |
| Vectors | Chroma (local, host 8005) | Avoids clashing with API :8000 |
| Async | Kafka | Uploads and agent turns; HTTP for chat |
| CI | GitHub Actions: ruff, pytest, Snyk | Shift Left on every push/PR |
| Local runtime | Docker Compose | Whole MVP on a laptop |

AWS ECS Fargate, API Gateway, Bedrock, and Atlas are **future / out of MVP**.
