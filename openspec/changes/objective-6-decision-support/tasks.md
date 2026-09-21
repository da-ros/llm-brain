## 1. Simulator Service foundation

- [ ] 1.1 Fill `services/simulator/` package (`__init__.py`, `main.py` FastAPI app, unauthenticated `GET /health` returning `service: simulator-service`)
- [ ] 1.2 Add `services/simulator/config.py` (pydantic-settings: port 8007, RAG URL, LLM URL, temperature 0, MongoDB, default sleep/meeting/focus hours) and pin versions in `services/simulator/requirements.txt`
- [ ] 1.3 Add correlation ID middleware and structured logging (`CorrelationFilter`, `X-Request-ID` generate-if-missing)
- [ ] 1.4 Add `services/simulator/Dockerfile`; register `simulator-service` on port 8007 in Docker Compose with `RAG_SERVICE_URL`, `LLM_SERVICE_URL`, and MongoDB

## 2. Decision tree and LLM reasoning

- [ ] 2.1 Implement the tree over sleep, time, money, and health families with defaults (7h / 3h / 4h / 0 prescriptions)
- [ ] 2.2 Emit 3 mandatory leaves (optimistic, baseline, pessimistic) plus up to 2 extra leaves when multiple families are present; cap at 5; record `trace` node ids
- [ ] 2.3 Call LLM Service `POST /chat` (Qwen3.5-4B base, temperature 0, `X-Request-ID`) with the question, variables, RAG excerpts, and leaf ids; parse JSON into `title`, `outcome`, and `assumptions` per scenario; retry once on invalid JSON; 502/504 and no persist if the model fails

## 3. RAG hydration and persistence

- [ ] 3.1 HTTP RAG client (`GET /search`) with `user_id` + `X-Request-ID`; skip RAG when client `variables` already cover detected families
- [ ] 3.2 Heuristic parse of sleep/meetings/spend/prescriptions from RAG text; on zero hits apply defaults and record “no personal context” assumptions; RAG 5xx/timeout while hydrating → 502/504 and no persist
- [ ] 3.3 Create MongoDB `simulations` collection with unique `correlation_id` and `user_id` index; upsert on simulate; list/get filter by `user_id`; cross-user id → 404
- [ ] 3.4 Expose `POST /simulate` (422 on blank question, 403 if free tier header/context) and `GET /simulations`, `GET /simulations/{id}`

## 4. MCP tool and API Router

- [ ] 4.1 Register Agents MCP tool `simulate_whatif` wrapping Simulator `POST /simulate`; `GET /mcp/tools` lists it; unknown tool still 404; do not change `reason_graph` / `learn_graph`
- [ ] 4.2 Add Router `SIMULATOR_SERVICE_URL` and `POST /api/simulate` (premium JWT, 10 req/min, 401/403/429, no Kafka); forward `X-Request-ID`
- [ ] 4.3 Add Router `GET /api/simulations` and `GET /api/simulations/{id}` (premium, 404 cross-user, 403 free)

## 5. Tests

- [ ] 5.1 Unit tests: tree always returns 3–5 scenarios with assumptions+trace; same inputs → same leaf traces; a successful simulate invokes the LLM client once and sets `llm_used` true; LLM 5xx does not persist
- [ ] 5.2 Unit tests: RAG hydrate path (hit, empty, 5xx); idempotent `correlation_id`; blank question 422
- [ ] 5.3 Unit tests: free 403, cross-user 404, MCP `simulate_whatif` listed and unknown tool 404
- [ ] 5.4 Integration tests: Router premium `POST /api/simulate` → Simulator 200 (mocked RAG and LLM); rate limit 429; list/get isolation

## 6. Documentation (output/)

- [ ] 6.1 Create `output/diagrams/simulator-architecture.drawio` (existing Frame 1.1/3/4/5 services in blue, Simulator in green, arrow to LLM :8003)
- [ ] 6.2 Create `output/diagrams/simulator-dataflow.drawio` (hydrate → tree → LLM `/chat` → persist → 200; RAG/LLM 5xx; free 403; MCP path; no Kafka)
- [ ] 6.3 Create `output/diagrams/README.md` with arrow legend and colour scheme
- [ ] 6.4 Create `output/documents/justificacion-ejemplo.md` with tree-plus-LLM vs Monte Carlo rationale, SOLID/patterns, and structured-log examples for `/simulate`, RAG hydrate, LLM `POST /chat`, `/simulations`, MCP `simulate_whatif`, and CorrelationFilter
