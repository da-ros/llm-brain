## Why

The platform needs a hybrid storage layer that combines binary/document storage (local
MongoDB with GridFS) with multimodal vector embeddings (Chroma, local) to enable
cross-modal semantic retrieval. The RAG service uses LangChain to perform Top-k retrieval
and inject relevant context into LLM queries.

This is **Objetivo Específico 3** of the thesis: the "Almacén híbrido y RAG" that
allows the LLM to reason over the user's personal knowledge.

### Context from Frame 1

Frame 1 established:
- **FastAPI backend** with JWT auth, config layer, and LLM provider abstraction
- **Local MongoDB** (GridFS) for binaries + records, **Chroma** for vector embeddings
- **Docker Compose** with local MongoDB and ChromaDB containers
- **Per-user data isolation** via `user_id` scoping
- **Fernet encryption** for application-level data protection

### Context from Frame 2

Frame 2 established:
- **ETL pipeline** that converts documents into structured JSON triples
- **JSONL output** at `data/triples/{user_id}/{doc_id}.jsonl`
- **Triple format**: `{"subject", "predicate", "object", "metadata"}`
- Frame 3 ingests these triples into the vector store for RAG

## What Changes

### Document & Binary Store (local MongoDB + GridFS)
- MongoDB client in `services/rag/document_store.py`
- Original binaries (text/pdf/image/video) stored in **MongoDB GridFS** (local container)
- Records (Documents index, task_status) with `user_id` field for per-user isolation
- CRUD operations with `user_id` filter on all queries

### Vector Store (Chroma, local)
- Vector store abstraction in `services/rag/vector_store.py`
- ChromaVectorStore class (local Chroma container; Pinecone is future/out of scope)
- Multimodal embedding generation with **Qwen3-VL-Embedding-2B** (2048-dim)
- Text chunks stored in Chroma alongside the vector (`document` field) with metadata linking to `gridfs_id`
- Fernet encryption for stored embeddings

### RAG Service (LangChain)
- RAG service in `services/rag/rag_service.py`
- Cross-modal semantic search with Top-k retrieval (text query can retrieve images/video)
- Document chunking with RecursiveCharacterTextSplitter
- Context injection for LLM queries

### FastAPI Integration
- Wire RAG service to file upload (after distillation)
- Wire RAG service to chat endpoint (context injection)
- RAG configuration: provider, chunk_size, top_k, encryption key

### Tests
- Unit tests for document store CRUD with user_id isolation
- Unit tests for vector store operations
- Unit tests for RAG retrieval quality
- Integration test: upload → distill → embed → retrieve → answer

## Output

```
output/
├── diagrams/
│   ├── rag-architecture.drawio    ← Architecture base diagram
│   ├── rag-dataflow.drawio        ← Data flow diagram
│   └── README.md
└── documents/
    └── justificacion-ejemplo.md   ← Component explanations + SOLID
```

## Capabilities

### New Capabilities
- `hybrid-store-rag`: Hybrid storage (local MongoDB/GridFS + Chroma) with LangChain RAG
  for cross-modal semantic retrieval and context injection

### Modified Capabilities
- `platform-foundation`: Added RAG configuration to config layer
- `memory-distillation`: RAG service ingests JSONL triples from Frame 2

## Impact

- New code: `services/rag/` (document_store, vector_store, rag_service)
- New dependencies: langchain, chromadb, Qwen3-VL-Embedding-2B (multimodal embeddings)
- Integrates with: Frame 2 (JSONL triples), Frame 4 (LLM provider for context)
- No changes to existing auth or ETL layers

## Execution Order

1. **Document store** — local MongoDB/GridFS client with per-user isolation
2. **Vector store** — Chroma (local) abstraction with encryption
3. **Embedding pipeline** — Qwen3-VL-Embedding-2B (2048-dim, multimodal) + chunking
4. **RAG service** — LangChain cross-modal retrieval + context injection
5. **Wire to FastAPI** — Upload and chat integration
6. **Test everything** — Unit + integration tests
