# Frame 2 — Memory Distillation Architecture Diagrams

Draw.io XML diagrams for One-Tap Memory Distillation (ETL Service :8001).

## Files

| File | What it shows |
|------|----------------|
| `etl-architecture.drawio` | Components. Blue = existing Frame 1/4. Green = this frame. |
| `etl-dataflow.drawio` | Numbered success path + error path. |

## Arrow direction (`etl-architecture.drawio`)

Solid = call / write. Dashed = response / later frame.

| From | To | Meaning |
|------|----|---------|
| Client | API Router :8000 | `POST /api/upload` + JWT |
| API Router | Client | **202** (does not wait for triples) |
| API Router | MongoDB GridFS | save original binary |
| API Router | Kafka | publish `file.uploaded` |
| Kafka | ETL consumer | consume job metadata (`file_id`, `user_id`) |
| ETL consumer | GridFS | fetch binary by `file_id` |
| GridFS | ETL consumer | bytes (dashed) |
| consumer | python-magic | MIME detect |
| python-magic | `select()` | Factory Method |
| `select()` | LangChain loaders | MIME → loader strategy |
| loaders | `distill()` | LangChain `Document`s |
| `distill()` | `llm_client` | loaded content |
| `llm_client` | LLM Service :8003 | `POST /extract` (base Qwen3.5-4B) |
| LLM Service | `llm_client` | JSON triples (dashed) |
| `distill()` | JSONL | `data/triples/{user_id}/{id}.jsonl` |
| `distill()` | Kafka producer | then producer → Kafka `task.response` |
| Kafka | API Router | consume `task.response`, update `task_status` (dashed) |
| JSONL | Frame 3 RAG | later ingestion (dashed; not this frame) |

There is **no** arrow from the client into ETL :8001. ETL has **no** upload HTTP endpoint (red box). Fine-tune adapters do **not** enter this service.

## Arrow direction (`etl-dataflow.drawio`)

1. Client → API Router → MIME/size gate → GridFS → Kafka `file.uploaded`.
2. API Router → 202 (dashed) back to the client **before** ETL runs.
3. Kafka → ETL consume → GridFS fetch → `select()` → LangChain `load()` → LLM `/extract` → triples (dashed) → JSONL.
4. JSONL → Kafka `task.response` → API Router `task_status=success` → `GET /tasks/:id` (dashed) → client.

Error arrows (red):

- MIME/size gate → 422 / 413 (Router, synchronous).
- LangChain `load()` fail → `task.response` `http_code=422` (no retry).
- LLM 5xx/timeout → `task.response` `http_code=500` (Router retries `file.uploaded`).

## Color scheme

- Blue (`#dae8fc`): Frame 1/1.1 Router, Kafka, client, LLM Service
- Green (`#d5e8d4`): ETL Service internals and LangChain loaders
- Yellow (`#fff2cc`): MIME / loader choice / JSON triples / JSONL
- Gray (`#f5f5f5`): GridFS, Frame 3
- Red (`#f8cecc`): errors and “no upload on ETL”

## How to open

Draw.io desktop, [app.diagrams.net](https://app.diagrams.net), or the VS Code Draw.io extension.

## References

- [Frame 1 diagrams](../../objective-1-0-architecture-repo/output/diagrams/)
- [Frame 1.1 API Router](../../objective-1-1-api-router/output/diagrams/)
- [Frame 4 LLM dataflow](../../objective-4-llm-inference-finetuning/output/llm/diagrams/) — ETL already appears there as `POST /extract`
