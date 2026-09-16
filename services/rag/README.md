# RAG Service — Hybrid Store + RAG

Standalone FastAPI service on **port 8002**. After Frame 2 writes JSONL triples,
this service chunks them, embeds them with **Qwen3-VL-Embedding-2B** (2048-dim,
multimodal), encrypts a Fernet copy, and stores **vector + chunk text +
`gridfs_id` metadata** in **Chroma** (local Docker, port 8005). Original
binaries stay in **MongoDB GridFS**. Chat uses Top-k retrieval and injects
context into the LLM Service (port 8003, base Qwen3.5-4B).

## Pipeline

```
POST /api/upload (API Router, 202)
    → GridFS + Kafka file.uploaded
    → ETL :8001 → JSONL
    → Kafka task.response
    → API Router POST RAG /ingest (201)
        → RecursiveCharacterTextSplitter (1000 / 200)
        → Qwen3-VL-Embedding-2B (2048-dim, text/image/video, one space)
        → Fernet ciphertext + Chroma ANN index
        → MongoDB Documents {_id, user_id, type, gridfs_id, triples_path, created_at}

POST /api/chat (Premium)
    → GET RAG /context
        → embed query (same 2048-dim space, cross-modal)
        → Top-k=3, filter user_id
        → decrypt chunk text
    → LLM :8003 with injected context
```

Upload stays **202** (Frame 2). `/ingest` returns **201** with `triples_count`.

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `API_PORT` | `8002` | RAG HTTP port |
| `MONGODB_URI` | `mongodb://localhost:27017` | Local MongoDB (GridFS + Documents) |
| `CHROMA_HOST` | `localhost` | Chroma HTTP host (`chroma` in Compose) |
| `CHROMA_PORT` | `8005` | Host port; inside Compose use `8000` |
| `VECTOR_STORE_PROVIDER` | `chroma` | MVP store. Pinecone is out of scope |
| `EMBEDDING_MODEL` | `Qwen/Qwen3-VL-Embedding-2B` | Multimodal 2048-dim embedder |
| `EMBEDDING_DIM` | `2048` | Default; MRL-truncatable to 1024/512/256 |
| `EMBEDDING_MOCK` | `true` | CI/laptop: hash embedder, no 2B download |
| `RAG_TOP_K` | `3` | Retrieval width |
| `RAG_CHUNK_SIZE` | `1000` | LangChain splitter |
| `RAG_CHUNK_OVERLAP` | `200` | LangChain splitter |
| `FERNET_KEY` | *(required in prod)* | Application-level encryption |

Set `EMBEDDING_MOCK=false` only when the Qwen3-VL-Embedding-2B weights are available.

## Local usage

```bash
docker compose up --build rag-service chroma mongo api-router etl-service llm-service kafka

curl http://localhost:8002/health
pytest services/rag/test_rag.py
```
