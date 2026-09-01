## Context

The hybrid store combines document storage (MongoDB Atlas) with vector embeddings
(Chroma/Pinecone) to enable semantic retrieval. The RAG service orchestrates
retrieval and context injection for LLM queries.

See proposal.md — Why. Depends on Frame 1 (FastAPI backend, MongoDB, Chroma) and
Frame 2 (JSONL triples output).

## Goals / Non-Goals

**Goals:**
- Store documents in MongoDB Atlas with per-user isolation
- Generate and store vector embeddings in Chroma/Pinecone
- Implement LangChain RAG with Top-k retrieval
- Encrypt embeddings at rest with Fernet
- Support document chunking for large files
- Ingest JSONL triples from Frame 2 into vector store

**Non-Goals:**
- Real-time streaming RAG
- Multi-modal retrieval (images)
- Graph-based knowledge representation

## Architecture Decisions

### 1. Document Store: MongoDB Atlas (M0 Free Tier)

**Decision**: MongoDB Atlas for document metadata and triples storage.

**Rationale**:
- Free tier (M0) sufficient for MVP
- Flexible schema for varying document types
- Native Python driver (motor/pymongo)
- Atlas search for text fallback

### 2. Vector Store: Chroma (local dev) / Pinecone (production)

**Decision**: Chroma for local development, Pinecone for production.

**Rationale**:
- Chroma: zero-config, runs in Docker, great for dev
- Pinecone: managed, scales, free starter tier
- Abstracted via LangChain vector store interface

### 3. Embedding Model: Sentence Transformers

**Decision**: Use sentence-transformers for embedding generation.

**Rationale**:
- Open source, runs locally
- Good multilingual support (Spanish + English)
- Compatible with LangChain

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
- Industry standard for RAG
- Built-in support for Chroma/Pinecone
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
        ├─ Generate embeddings (sentence-transformers)
        ├─ Encrypt with Fernet
        └─ Store in Chroma/Pinecone
        │
        ▼
User query (natural language)
        │
        ▼
RAG Retrieval
        │
        ├─ Embed query
        ├─ Semantic search (Top-k=3)
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
| Pinecone free tier limits (100k vectors) | Monitor usage, upgrade path ready |
| Embedding quality on Spanish text | Use multilingual model, validate with sample queries |
| Large document chunking overhead | Process asynchronously, chunk cache |

## Decisions Made

- Document schema: `{_id, user_id, type, original_path, triples_path, created_at}`
- Embedding schema: `{_id, document_id, vector, metadata, encrypted: true}`
- Vector dimensions: 384 (sentence-transformers default)
- Top-k retrieval: k=3 (configurable via env)
- Chunk size: 1000 chars, overlap: 200 chars
- Encryption: Fernet symmetric (key via FERNET_KEY env var)

## Design Patterns & SOLID Principles

### Patterns Used

| Pattern | Where | Purpose |
|---------|-------|---------|
| **Strategy** | `VectorStore` protocol + ChromaVectorStore/PineconeVectorStore | Each vector store is a strategy; RAG service selects the right one at runtime |
| **Factory Method** | `create_vector_store(provider)` | Creates the correct vector store based on config without knowing the concrete class |
| **Adapter** | Vector store wrappers | Adapts Chroma/Pinecone APIs to a common interface |
| **Facade** | `rag_service.py` | Hides retrieval complexity behind `semantic_search()` and `context_injection()` |
| **Repository** | `document_store.py` | Encapsulates MongoDB data access behind a clean interface |

### SOLID Principles Applied

| Principle | Application |
|-----------|-------------|
| **S — Single Responsibility** | `document_store` only handles MongoDB. `vector_store` only handles embeddings. `rag_service` only orchestrates retrieval. |
| **O — Open/Closed** | Adding a new vector store (e.g., Weaviate) requires ONLY creating a new class — zero changes to RAG service. |
| **L — Liskov Substitution** | Any `VectorStore` implementation can replace another without breaking `rag_service`. |
| **I — Interface Segregation** | `VectorStore` protocol has only essential methods (`add`, `search`, `delete`) — minimal contract. |
| **D — Dependency Inversion** | `rag_service` depends on `VectorStore` abstraction, not on Chroma/Pinecone concrete classes. |
