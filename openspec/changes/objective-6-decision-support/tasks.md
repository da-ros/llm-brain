## Tasks

### A. Simulator Core

- [ ] A.1 Define `Scenario` dataclass: name, description, assumptions, outcome, confidence, source_docs
- [ ] A.2 Implement `SimulatorEngine` in `services/simulator/engine.py`
      — generate_scenarios(query, context) -> list[Scenario]
- [ ] A.3 Implement assumption extraction: LLM -> structured assumptions with source links

### B. Scenario Generation

- [ ] B.1 Implement scenario prompt template: "Generate N scenarios for: {query}"
- [ ] B.2 Implement assumption tracing: link each assumption to source document
- [ ] B.3 Implement confidence scoring: LLM assesses scenario plausibility
- [ ] B.4 Add scenario ranking: sort by confidence score

### C. Integration

- [ ] C.1 Wire simulator to RAG service for context retrieval
- [ ] C.2 Implement POST /api/simulate endpoint
- [ ] C.3 Add per-user isolation: scenarios scoped to user's data
- [ ] C.4 Add scenario caching (optional, for repeated queries)

### D. Web Dashboard Integration

- [ ] D.1 Define API response format for web consumption
- [ ] D.2 Implement scenario comparison view (frontend spec)
- [ ] D.3 Add assumption detail view (expandable per assumption)

### E. Testing & Validation

- [ ] E.1 Unit tests for scenario generation (mock LLM)
- [ ] E.2 Unit tests for assumption extraction and tracing
- [ ] E.3 Integration test: query -> RAG -> simulate -> scenarios
- [ ] E.4 Validate determinism: same input -> same output (within confidence)
- [ ] E.5 Validate assumption quality: all assumptions traceable to source docs
