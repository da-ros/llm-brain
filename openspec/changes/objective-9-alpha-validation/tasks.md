## Tasks

### A. Test Infrastructure

- [ ] A.1 Set up test database (MongoDB test instance, isolated per test run)
- [ ] A.2 Set up test fixtures: mock LLM responses, sample documents, test users
- [ ] A.3 Configure pytest with markers: unit, integration, slow
- [ ] A.4 Add coverage reporting (pytest-cov)

### B. Unit Tests

- [ ] B.1 Auth tests: register, login, token validation, bcrypt hashing
- [ ] B.2 Config tests: defaults, required secrets, provider resolution
- [ ] B.3 ETL tests: each parser (PDF, HTML, EML, OCR), triple extraction
- [ ] B.4 RAG tests: vector store operations, embedding generation
- [ ] B.5 Simulator tests: scenario generation, assumption extraction
- [ ] B.6 Shield tests: heuristics, embedding similarity, alerts

### C. Integration Tests

- [ ] C.1 FastAPI + MongoDB: CRUD operations with user_id isolation
- [ ] C.2 Full pipeline: upload -> distill -> embed -> chat -> response
- [ ] C.3 Auth flow: register -> login -> access protected endpoint
- [ ] C.4 Multi-user isolation: user A cannot access user B's data

### D. KPI Measurement

- [ ] D.1 Implement latency measurement: API response times (p50, p95, p99)
- [ ] D.2 Implement RAG precision: Top-3 retrieval accuracy on test queries
- [ ] D.3 Implement throughput: requests per second under normal load
- [ ] D.4 Create KPI report template (markdown)

### E. Performance Benchmarks

- [ ] E.1 Benchmark: API health endpoint latency
- [ ] E.2 Benchmark: Chat endpoint latency (with/without RAG)
- [ ] E.3 Benchmark: File upload + distillation time
- [ ] E.4 Document benchmark results with hardware specs

### F. Architecture Validation

- [ ] F.1 Compare C4 Level 1 diagram against implemented components
- [ ] F.2 Compare C4 Level 2 containers against actual services
- [ ] F.3 Compare C4 Level 3 components against actual modules
- [ ] F.4 Document any deviations from original architecture

### G. Video Demo

- [ ] G.1 Write demo script (5-10 minutes, covers all features)
- [ ] G.2 Record demo: upload document -> chat -> analytics -> simulator
- [ ] G.3 Add narration explaining architecture decisions
- [ ] G.4 Export as MP4 (1080p minimum)

### H. Documentation

- [ ] H.1 Update README with final architecture and setup instructions
- [ ] H.2 Document KPI results in thesis document
- [ ] H.3 Document architecture deviations in docs/architecture/decisions.md
- [ ] H.4 Create demo script transcript for thesis defense
