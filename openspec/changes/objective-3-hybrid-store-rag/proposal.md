## Why

The platform needs a hybrid storage layer that combines document storage (MongoDB Atlas)
with vector embeddings (Chroma/Pinecone) to enable semantic retrieval. The RAG service
uses LangChain to perform Top-k retrieval and inject relevant context into LLM queries.

This is **Objetivo Específico 3** of the thesis: the "Almacén híbrido y RAG" that
allows the LLM to reason over the user's personal knowledge.

### Context from Frame 1

Frame 1 established:
- **FastAPI backend** with JWT auth, config layer, and LLM provider abstraction
- **MongoDB** for document storage, **Chroma** for vector embeddings
- **Docker Compose** with MongoDB 7 and ChromaDB containers
- **Per-user data isolation** via `user_id` scoping
- **Fernet encryption** for application-level data protection

### Context from Frame 2

Frame 2 established:
- **ETL pipeline** that converts documents into structured JSON triples
- **JSONL output** at `data/triples/{user_id}/{doc_id}.jsonl`
- **Triple format**: `{"subject", "predicate", "object", "metadata"}`
- Frame 3 ingests these triples into the vector store for RAG

## What Changes

### Document Store (MongoDB)
- MongoDB client in `services/rag/document_store.py`
- Document schema with `user_id` field for per-user isolation
- CRUD operations with `user_id` filter on all queries

### Vector Store (Chroma/Pinecone)
- Vector store abstraction in `services/rag/vector_store.py`
- ChromaVectorStore and PineconeVectorStore classes
- Embedding generation with sentence-transformers
- Fernet encryption for stored embeddings

### RAG Service (LangChain)
- RAG service in `services/rag/rag_service.py`
- Semantic search with Top-k retrieval
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
- `hybrid-store-rag`: Hybrid storage (MongoDB + Chroma/Pinecone) with LangChain RAG
  for semantic retrieval and context injection

### Modified Capabilities
- `platform-foundation`: Added RAG configuration to config layer
- `memory-distillation`: RAG service ingests JSONL triples from Frame 2

## Impact

- New code: `services/rag/` (document_store, vector_store, rag_service)
- New dependencies: langchain, chromadb, sentence-transformers, pinecone-client
- Integrates with: Frame 2 (JSONL triples), Frame 4 (LLM provider for context)
- No changes to existing auth or ETL layers

## Execution Order

1. **Document store** — MongoDB client with per-user isolation
2. **Vector store** — Chroma/Pinecone abstraction with encryption
3. **Embedding pipeline** — sentence-transformers + chunking
4. **RAG service** — LangChain retrieval + context injection
5. **Wire to FastAPI** — Upload and chat integration
6. **Test everything** — Unit + integration tests
