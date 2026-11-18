# OSS stack

Source of truth for how this stack runs: [current-runtime.md](current-runtime.md)
and `openspec/input/context.txt`.

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Language | Python 3.13 | Async FastAPI, first-class typing, thesis runtime |
| API | FastAPI + uvicorn | Health, JWT dependencies, OpenAPI for the defense |
| Settings | pydantic-settings | Env vars from Compose or the host `.env`, fail-fast validation |
| Auth | JWT (HS256) + PBKDF2-HMAC-SHA256 | Multi-tenant `user_id` + `subscription_tier`. Hash is `salt$hash`, 200000 iterations |
| LLM protocol | `LLMProvider` | One caller path for the host process |
| Host LLM | Qwen3.5-4B **base** on port 8003 | `LLM_BACKEND=qwen_local` (PyTorch / Metal) or `ollama`. Not a Compose service. Not Bedrock |
| On-device LLM | Qwen3.5-4B GGUF Q4_K_M via `llama.rn` | llama.cpp on the iPhone GPU (Metal). Free = base pack. Premium = that user's LoRA pack |
| Embeddings | Qwen3-VL-Embedding-2B, 2048-dim | Same family. `EMBEDDING_MOCK=true` keeps CI off the weights |
| Documents | MongoDB 7 + GridFS (local container) | Binaries and task status |
| Vectors | Chroma (local container, host port 8005) | ANN index of the raw vectors. Fernet covers chunk text and a ciphertext copy of each vector |
| Async | Kafka | Uploads and `session.turn.completed`. HTTP for chat |
| CI | GitHub Actions: ruff, pytest, Snyk | Feature branches run the mocked suite. `main` builds the nine service images |
| Local runtime | Docker Compose plus two host processes | Compose runs the services. Ports 8003 and 8004 are processes on the Mac |

AWS ECS Fargate, API Gateway, Bedrock, and Atlas are future work, outside the MVP.

Chart.js is the library named in the anteproyecto. The Life Analytics screen
draws its own scatter in React. Recharts ships in the UI kit and is not that screen.
