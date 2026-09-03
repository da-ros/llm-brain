## 1. Agents Service foundation

- [ ] 1.1 Create `services/agents/` package (`__init__.py`, `main.py` FastAPI app, health `GET /health`)
- [ ] 1.2 Add `services/agents/config.py` (pydantic-settings: port 8006, RAG/LLM/Fine-Tune URLs, Kafka topic, score threshold, batch min items) and pin `langgraph` in `services/agents/requirements.txt`
- [ ] 1.3 Add correlation ID middleware and structured logging (`CorrelationFilter`, `X-Request-ID`)
- [ ] 1.4 Add `services/agents/Dockerfile` and `requirements.txt`; register service in Docker Compose

## 2. MCP host, LangGraph, and data stores

- [ ] 2.1 Define Agent/tool registry (`GET /mcp/tools`, `POST /mcp/tools/{name}`, 404 on unknown tool)
- [ ] 2.2 Add LangGraph TypedDict state and compile `reason_graph` (retrieve → generate → assumptions / error END)
- [ ] 2.3 Compile `learn_graph` (ingest → evaluate → maybe_append_batch); graphs call RAG/LLM/Fine-Tune only via HTTP
- [ ] 2.4 Create MongoDB collections and indexes: `agent_interactions` (unique `correlation_id`), `agent_feedback`, `finetune_batches`
- [ ] 2.5 Enforce premium-only + `user_id` isolation on agent write/read helpers (403 free, 404 cross-user)

## 3. Razonador (sync reason_graph)

- [ ] 3.1 Implement retrieve node: HTTP RAG with `X-Request-ID` and `user_id`
- [ ] 3.2 Implement generate node: HTTP LLM `/chat`; map 5xx/timeout to graph error → HTTP 502/504
- [ ] 3.3 Implement assumptions node; include "no personal context" when RAG is empty
- [ ] 3.4 Expose `POST /reason` as facade over `reason_graph.invoke`; `GET /health` reports `orchestrator: langgraph`

## 4. Ingestor and Evaluador (async learn_graph)

- [ ] 4.1 Implement Kafka consumer for `session.turn.completed` that invokes `learn_graph`
- [ ] 4.2 Implement ingest node: upsert interaction; idempotent on `correlation_id`
- [ ] 4.3 Implement evaluate node: heuristic score, persist `agent_feedback`, never call Fine-Tune `POST /train`
- [ ] 4.4 Implement maybe_append_batch node for `(user_id, ISO week)`; status `accumulating` / `ready`

## 5. Manual fine-tune trigger

- [ ] 5.1 Implement `POST /batches/{batch_id}/trigger` (409 if not `ready` or empty)
- [ ] 5.2 Export batch items to JSONL `dataset_path` and call Fine-Tune Service `POST /train`; store `job_id`, status `submitted`

## 6. API Router integration

- [ ] 6.1 Premium `POST /api/chat` calls Agents `POST /reason` instead of RAG+LLM directly; return assumptions
- [ ] 6.2 After 200, publish Kafka `session.turn.completed` (same `X-Request-ID`); Free chat skips agents and Kafka
- [ ] 6.3 Add `POST /api/sessions/end` (premium 202, free 403)
- [ ] 6.4 Add `POST /api/finetune` with `batch_id` (422 if missing; 202 with `job_id`); add `CHAT_VIA_AGENTS` rollback flag

## 7. Tests

- [ ] 7.1 Unit tests: `reason_graph` with mocked RAG/LLM (context hit, empty RAG, LLM 5xx)
- [ ] 7.2 Unit tests: `learn_graph` ingest idempotency and Evaluador does not auto-train
- [ ] 7.3 Unit tests: Free 403, cross-user 404, unknown MCP tool 404
- [ ] 7.4 Integration tests: Router premium chat → reason_graph → Kafka → learn_graph; manual trigger → mocked Fine-Tune

## 8. Documentation (output/)

- [ ] 8.1 Create `output/diagrams/agents-architecture.drawio` (existing services in blue, Agents Service in green)
- [ ] 8.2 Create `output/diagrams/agents-dataflow.drawio` (reason_graph + Kafka learn_graph + manual train + error paths)
- [ ] 8.3 Create `output/diagrams/README.md`
- [ ] 8.4 Create `output/documents/justificacion-ejemplo.md` with LangGraph vs LangChain rationale, SOLID/patterns, and structured-log examples for `/reason`, Kafka `learn_graph`, `/batches/{id}/trigger`, and CorrelationFilter
