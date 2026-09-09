## Context

The hybrid store combines binary/document storage (local MongoDB with GridFS) with
multimodal vector embeddings (Chroma, local) to enable cross-modal semantic retrieval.
The RAG service orchestrates retrieval and context injection for LLM queries.

See proposal.md — Why. Depends on Frame 1 (FastAPI backend, MongoDB, Chroma) and
Frame 2 (JSONL triples output).

## Goals / Non-Goals

**Goals:**
- Store original binaries in local MongoDB GridFS and records in MongoDB, with per-user isolation
- Generate and store multimodal vector embeddings (2048-dim) in Chroma (local)
- Store text chunks in Chroma alongside the vector (`document` field), with metadata linking to `gridfs_id`
- Implement LangChain RAG with Top-k, cross-modal retrieval
- Encrypt embeddings at rest with Fernet
- Support document chunking for large files
- Ingest JSONL triples from Frame 2 into vector store

**Non-Goals:**
- Real-time streaming RAG
- Graph-based knowledge representation
- Cloud deployment / Pinecone / AWS (future work, out of MVP scope)

## Architecture Decisions

### 1. Binary & Document Store: local MongoDB + GridFS

**Decision**: Local MongoDB (Docker container) with GridFS for original binaries
(text/pdf/image/video) and MongoDB collections for records (Documents index, task_status).

**Rationale**:
- Runs $0 in a local Docker container (no Atlas, no cloud) for the MVP
- GridFS stores full binaries of any modality; `gridfs_id` referenced from Documents
- Flexible schema for varying document types
- Native Python driver (motor/pymongo)
- Chroma does NOT store raw binaries, so MongoDB is required for binaries + records

### 2. Vector Store: Chroma (local)

**Decision**: Chroma running in a local Docker container as the single vector store for the MVP.

**Rationale**:
- Chroma: zero-config, runs in Docker, great for local dev, $0
- Stores 2048-dim embeddings for all modalities in one collection (cross-modal)
- Stores the text chunk alongside the vector (`document` field) + metadata linking to `gridfs_id`
- Abstracted via LangChain vector store interface
- Pinecone / managed cloud vector stores are **future work**, out of MVP scope

### 3. Embedding Model: Qwen3-VL-Embedding-2B (2048-dim, multimodal)

**Decision**: Use Qwen3-VL-Embedding-2B for embedding generation (2048 dimensions by default).

**Rationale**:
- Multimodal: embeds text, images, screenshots AND video into ONE shared 2048-dim space,
  enabling cross-modal retrieval (e.g. search images with a text query)
- Family alignment with the inference model Qwen3.5-4B (same tokenizer/conceptual space,
  same fine-tuning toolchain)
- Greater semantic capacity than a 384-dim text-only model (all-MiniLM was text-only)
- Matryoshka Representation Learning (MRL): the 2048-dim vector can be truncated to
  1024/512/256 with minor accuracy loss to save storage/latency; **default is 2048**
- Runs locally; compatible with LangChain and Chroma

### 4. Chunking Strategy: Recursive Character Splitter

**Decision**: LangChain RecursiveCharacterTextSplitter (1000 chars, 200 overlap).

**Rationale**:
- Preserves sentence boundaries
- Overlap maintains context across chunks
- Standard approach in RAG systems

### 5. Encryption: Fernet (Application-Level)

**Decision**: Encrypt embeddings before storage with Fernet symmetric encryption.

**Rationale**:
- Application-level control (not provider-dependent)
- Fernet provides authenticated encryption
- Key managed via environment variable

### 6. RAG Retrieval: LangChain with Top-k

**Decision**: Use LangChain for retrieval orchestration with configurable Top-k.

**Rationale**:
- Industry standard for RAG; LangChain remains the RAG stack
- Built-in support for Chroma
- Cross-modal Top-k retrieval over the shared 2048-dim space
- Easy to swap vector stores

## Data Flow

```
Frame 2 JSONL triples
        │
        ▼
RAG Ingestion Pipeline
        │
        ├─ Read JSONL: data/triples/{user_id}/{doc_id}.jsonl
        ├─ Chunk text (RecursiveCharacterTextSplitter)
        ├─ Generate embeddings (Qwen3-VL-Embedding-2B, 2048-dim, multimodal)
        ├─ Encrypt with Fernet
        └─ Store in Chroma (vector + text chunk + metadata→gridfs_id); binaries in GridFS
        │
        ▼
User query (natural language)
        │
        ▼
RAG Retrieval
        │
        ├─ Embed query (Qwen3-VL-Embedding-2B, shared 2048-dim space)
        ├─ Cross-modal semantic search (Top-k=3; can match text, image, video)
        ├─ Decrypt results
        └─ Inject context into LLM prompt
        │
        ▼
LLM response with relevant context
```

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| Chroma data loss on container restart | Persistent volume mount in Docker |
| 1 GB embedding budget with 2048-dim vectors | Matryoshka (MRL) truncation to 1024/512/256 if needed; default 2048 |
| Embedding quality on Spanish text | Qwen3-VL-Embedding-2B multilingual + multimodal, validate with sample queries |
| Large document chunking overhead | Process asynchronously, chunk cache |

## Decisions Made

- Document schema: `{_id, user_id, type, gridfs_id, triples_path, created_at}` (binary in GridFS)
- Embedding schema: `{_id, document_id, vector, modality, chunk_text, metadata, encrypted: true}`
- Vector dimensions: 2048 (Qwen3-VL-Embedding-2B default; MRL-truncatable to 1024/512/256)
- Modalities: text, image, video embedded into one shared 2048-dim space (cross-modal)
- Top-k retrieval: k=3 (configurable via env)
- Chunk size: 1000 chars, overlap: 200 chars
- Encryption: Fernet symmetric (key via FERNET_KEY env var)

## Design Patterns & SOLID Principles

### Patterns Used

| Pattern | Where | Purpose |
|---------|-------|---------|
| **Strategy** | `VectorStore` protocol + ChromaVectorStore (MVP; future stores are additional strategies) | Each vector store is a strategy; RAG service selects the right one at runtime |
| **Factory Method** | `create_vector_store(provider)` | Creates the correct vector store based on config without knowing the concrete class |
| **Adapter** | Vector store wrappers | Adapts the Chroma API to a common interface (future stores plug in the same way) |
| **Facade** | `rag_service.py` | Hides retrieval complexity behind `semantic_search()` and `context_injection()` |
| **Repository** | `document_store.py` | Encapsulates MongoDB data access behind a clean interface |

### SOLID Principles Applied

| Principle | Application |
|-----------|-------------|
| **S — Single Responsibility** | `document_store` only handles MongoDB. `vector_store` only handles embeddings. `rag_service` only orchestrates retrieval. |
| **O — Open/Closed** | Adding a new vector store (e.g., Weaviate) requires ONLY creating a new class — zero changes to RAG service. |
| **L — Liskov Substitution** | Any `VectorStore` implementation can replace another without breaking `rag_service`. |
| **I — Interface Segregation** | `VectorStore` protocol has only essential methods (`add`, `search`, `delete`) — minimal contract. |
| **D — Dependency Inversion** | `rag_service` depends on the `VectorStore` abstraction, not on the concrete Chroma class. |
