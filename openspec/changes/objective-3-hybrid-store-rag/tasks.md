## Tasks

### A. Document Store (MongoDB)

- [x] A.1 Implement MongoDB client in `services/rag/document_store.py`
      — connect(), insert_document(), get_document(), list_documents(user_id)
- [x] A.2 Define document schema with user_id field for per-user isolation
- [x] A.3 Implement CRUD operations with user_id filter on all queries
- [x] A.4 Add connection pooling and error handling

### B. Vector Store (Chroma/Pinecone)

- [x] B.1 Implement vector store abstraction in `services/rag/vector_store.py`
      — ChromaVectorStore and PineconeVectorStore classes
- [x] B.2 Implement embedding generation with sentence-transformers
- [x] B.3 Implement Fernet encryption for stored embeddings
- [x] B.4 Add vector store factory: `create_vector_store(provider)` that selects by config

### C. RAG Service (LangChain)

- [x] C.1 Implement RAG service in `services/rag/rag_service.py`
      — semantic_search(), top_k_retrieval(), context_injection()
- [x] C.2 Implement document chunking with RecursiveCharacterTextSplitter
- [x] C.3 Wire RAG service to LLM provider for context-augmented generation
- [x] C.4 Add per-user isolation: all queries filtered by user_id

### D. Integration

- [x] D.1 Wire RAG service to file upload endpoint (after distillation)
- [x] D.2 Wire RAG service to chat endpoint (context injection)
- [x] D.3 Add RAG configuration: provider, chunk_size, top_k, encryption key

### E. Testing & Validation

- [x] E.1 Unit tests for document store CRUD with user_id isolation
- [x] E.2 Unit tests for vector store operations (mock Chroma/Pinecone)
- [x] E.3 Unit tests for RAG retrieval quality (known documents, known queries)
- [x] E.4 Integration test: upload → distill → embed → retrieve → answer
- [x] E.5 Validate encryption: embeddings encrypted at rest, decrypted on retrieval

### F. Documentation (output/documents/)

- [x] F.1 Create `output/documents/justificacion-ejemplo.md`
      — Component explanations, design patterns (Strategy, Factory, Adapter, Facade, Repository), SOLID principles
- [x] F.2 Document design patterns used: Strategy, Factory Method, Adapter, Facade, Repository
- [x] F.3 Document SOLID principles applied: SRP, OCP, LSP, ISP, DIP
