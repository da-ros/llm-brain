# Frame 3 — Hybrid Store + RAG Architecture Diagrams

Draw.io XML for the hybrid store (local MongoDB/GridFS + Chroma) and LangChain RAG.

## Files

| File | What it shows |
|------|----------------|
| `rag-architecture.drawio` | Components. Blue = existing Frame 1/1.1/2/4. Green = this frame. |
| `rag-dataflow.drawio` | Numbered ingest + retrieval + error paths. |

## Arrow direction (`rag-architecture.drawio`)

Solid = call / write. Dashed = HTTP 202/200/201, GridFS bytes, Chroma hits, LLM response.

| From | To | Meaning |
|------|----|---------|
| Client | API Router :8000 | `POST /api/upload` and `POST /api/chat` + JWT |
| API Router | Client | **202** (upload) / **200** (chat) — upload does **not** wait for embeddings |
| API Router | Kafka | publish `file.uploaded` (Frame 2) |
| Kafka | ETL :8001 | consume job |
| ETL | JSONL | write `data/triples/{user_id}/{id}.jsonl` |
| ETL | Kafka | `task.response` |
| Kafka | API Router | success (dashed) |
| API Router | RAG :8002 | **POST /ingest** after distillation (this frame) |
| API Router | RAG :8002 | **GET /context** on Premium chat |
| RAG | API Router | **201** ingest / context string (dashed) |
| JSONL | RAG | read triples |
| RAG FastAPI | Document Store | insert Documents row |
| Document Store | MongoDB GridFS | metadata + `gridfs_id` (binaries already stored at upload) |
| MongoDB | Embedding pipeline | image/video bytes for cross-modal embed (dashed) |
| RAG FastAPI | LangChain splitter | chunk 1000 / overlap 200 |
| Splitter | Qwen3-VL-Embedding-2B | text chunks |
| Embedder | Vector Store | 2048-dim vector + Fernet ciphertext |
| Vector Store | Chroma :8005 | add `embeddings` + `documents` + `metadata.gridfs_id` |
| RAG Facade | Chroma | Top-k search filtered by `user_id` |
| Chroma | RAG Facade | hits, then Fernet decrypt (dashed) |
| API Router | LLM :8003 | prompt + RAG context |
| LLM :8003 | API Router | generated answer (dashed) |

There is **no** arrow from the client into RAG :8002 (the Router is the gateway). There is **no** Pinecone, MongoDB Atlas, or AWS Bedrock box in the live path (red callout).

## Arrow direction (`rag-dataflow.drawio`)

### Flow 1 — Ingestion

1. Frame 2 JSONL → API Router (after `task.response` success) → RAG `POST /ingest`.
2. Read JSONL → LangChain chunk (1000/200) → Qwen3-VL-Embedding-2B (2048-dim).
3. Optional GridFS image/video bytes → **same** embedder / same collection (dashed up into step 5).
4. Fernet encrypts the stored copy + chunk_text → Chroma (`vector` + `document` + `metadata→gridfs_id`).
5. RAG also writes the Documents index in MongoDB (`user_id`, `type`, `gridfs_id`, `triples_path`).
6. **201** `{triples_count}` dashed back to the Router (upload itself already returned 202).

### Flow 2 — Retrieval

1. Client → API Router `POST /api/chat` → RAG `GET /context`.
2. Embed query in the **same 2048-dim space** → cross-modal Top-k=3 with `user_id` filter.
3. Query vector **into** Chroma; hits **back** to the Top-k node (dashed).
4. Decrypt chunk_text → context injection → **back** to the Router (dashed).
5. Router → LLM :8003 with prompt+context; LLM answer dashed to **200 OK** → client.

### Flow 3 — Errors (red)

| From | To | Meaning |
|------|----|---------|
| Read JSONL | missing file | `triples_count=0` |
| Chroma | HTTP 500 | store down on `/search` or `/ingest` |
| Documents index | HTTP 404 | wrong `user_id` (never reveal existence) |
| Embedder | HTTP 500 | model/runtime failure |
| Chat (Free tier) | skip RAG | no `GET /context` |

## Color scheme

- Blue (`#dae8fc`): Frame 1/1.1 Router, Kafka, client, LLM Service
- Green (`#d5e8d4`): RAG Service internals and ingest 201
- Yellow (`#fff2cc`): JSONL / chunking / Fernet / Top-k
- Gray (`#f5f5f5`): MongoDB GridFS, Chroma
- Red (`#f8cecc`): errors and “no Atlas/Pinecone/Bedrock”

## How to open

Draw.io desktop, [app.diagrams.net](https://app.diagrams.net), or the VS Code Draw.io extension.

## References

- [Frame 1 diagrams](../../objective-1-0-architecture-repo/output/diagrams/)
- [Frame 1.1 API Router](../../objective-1-1-api-router/output/diagrams/)
- [Frame 2 ETL diagrams](../../objective-2-memory-distillation/output/diagrams/)
- [Frame 4 LLM](../../objective-4-llm-inference-finetuning/output/llm/diagrams/) — chat already accepts RAG `context`
