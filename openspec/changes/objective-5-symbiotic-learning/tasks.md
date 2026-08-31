## Tasks

### A. Agent Framework

- [ ] A.1 Define `Agent` protocol in `services/agents/base.py`
      — process(input: AgentInput) -> AgentOutput
- [ ] A.2 Define `AgentInput` and `AgentOutput` dataclasses
- [ ] A.3 Implement agent registry: register(), get_agent(), list_agents()

### B. Ingestor Agent

- [ ] B.1 Implement `IngestorAgent` in `services/agents/ingestor.py`
      — Processes user interactions into structured training data
- [ ] B.2 Add interaction logging: capture query, response, context, timestamp
- [ ] B.3 Add anonymization: strip PII from training data
- [ ] B.4 Store ingested data in MongoDB with user_id isolation

### C. Razonador Agent

- [ ] C.1 Implement `RazonadorAgent` in `services/agents/razonador.py`
      — Reasons over user context and generates suggestions
- [ ] C.2 Implement context aggregation: combine user history, preferences, recent queries
- [ ] C.3 Implement suggestion generation: use LLM to generate contextual suggestions
- [ ] C.4 Add confidence scoring for generated suggestions

### D. Evaluador Agent

- [ ] D.1 Implement `EvaluadorAgent` in `services/agents/evaluador.py`
      — Scores output quality and decides on fine-tuning trigger
- [ ] D.2 Implement quality scoring: relevance, accuracy, completeness
- [ ] D.3 Implement fine-tuning trigger: score < threshold -> flag for fine-tune
- [ ] D.4 Add scoring history and trend tracking

### E. Fine-Tuning Batch System

- [ ] E.1 Implement batch collector: accumulate interactions until batch size reached
- [ ] E.2 Implement manual fine-tuning trigger endpoint (`POST /api/finetune`)
- [ ] E.3 Implement training data export: batch -> Bedrock training format
- [ ] E.4 Add fine-tuning status tracking and completion notification

### F. Integration & Testing

- [ ] F.1 Wire agents to chat endpoint (post-response processing)
- [ ] F.2 Unit tests for each agent (mock LLM calls)
- [ ] F.3 Integration test: query -> ingest -> reason -> evaluate -> fine-tune
- [ ] F.4 End-to-end test: full learning loop with manual trigger
