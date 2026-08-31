## Tasks

### A. Heuristic Detection

- [ ] A.1 Implement pattern matcher in `services/shield/heuristics.py`
      — SSN, credit card, phone, email patterns (regex)
- [ ] A.2 Implement keyword detector: urgency words ("urgent", "verify", "suspended")
- [ ] A.3 Implement URL analyzer: suspicious domains, shortened URLs
- [ ] A.4 Add confidence scoring for each detection

### B. Embedding Similarity Detection

- [ ] B.1 Implement scam pattern database (known scam templates as embeddings)
- [ ] B.2 Implement similarity search: document embedding vs scam embeddings
- [ ] B.3 Add cosine similarity threshold (> 0.8 = match)
- [ ] B.4 Integrate with existing vector store (Chroma/Pinecone)

### C. Alert System

- [ ] C.1 Implement alert data model: severity, type, description, document_id, timestamp
- [ ] C.2 Implement alert storage in MongoDB with user_id isolation
- [ ] C.3 Implement alert API: GET /api/alerts (list), POST /api/alerts/{id}/dismiss
- [ ] C.4 Add alert count badge (for UI integration)

### D. Integration

- [ ] D.1 Add post-upload hook: scan document after distillation
- [ ] D.2 Implement on-demand scan endpoint: POST /api/scan/{document_id}
- [ ] D.3 Wire alerts to web dashboard (notification panel)
- [ ] D.4 Add per-user isolation: alerts scoped to user's documents

### E. Testing & Validation

- [ ] E.1 Unit tests for heuristics (known patterns, edge cases)
- [ ] E.2 Unit tests for embedding similarity (mock vector store)
- [ ] E.3 Unit tests for alert CRUD with user_id isolation
- [ ] E.4 Integration test: upload -> scan -> alert generated
- [ ] E.5 Validate false positive rate on sample documents
