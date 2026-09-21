## Why

Premium users can already retrieve personal context (Frame 3) and receive
assumption-traced answers (Frame 5), but they cannot ask “what if…?” and see
alternative futures. Decision fatigue — one of the four pains in the
anteproyecto — needs a simulator that makes 3–5 scenarios with **explicit,
traceable assumptions**. The structure stays a simple decision tree (not
Monte Carlo). The **reasoning** of each scenario is done by **Qwen3.5-4B**
in the local LLM Service, the same way ETL asks the model to reason before
it emits triples. Frame 6 adds that value module so the Brain can support
choice, not only recall.

## Context from Frame 1.1 and Frame 3

- **Frame 1.1 (API Router, port 8000)**: JWT, `X-Request-ID`, rate limits,
  premium/free gating. Clients never address backend ports directly. Router
  is a facade (no business logic).
- **Frame 3 (RAG, port 8002)**: MongoDB + Chroma, Fernet embeddings, Top-k
  retrieval scoped by `user_id`. HTTP `GET /search` and context injection.
  Simulator **reads** personal context through this API; it does not own
  Chroma or GridFS.
- **Frame 4 (LLM, port 8003)**: Qwen3.5-4B **base** container. Simulator
  calls `POST /chat` (temperature 0) to reason over the tree leaves and
  the user's context. It does not load model weights.
- **Frame 5 (Agents, port 8006)** is **not** a hard build dependency
  (`context.txt`: Frame 6 depends on 1.1 + 3, parallel with Frame 8), but
  the MCP host already exists. Frame 6 **registers** the `simulate_whatif`
  tool on that host using the same HTTP-wrapper pattern as `rag_search`.
  If Agents is down, `POST /api/simulate` still works (Router → Simulator).

Frame 6 does **not** replace RAG, Agents, or chat. It is a sibling value
module. Monte Carlo, stochastic optimisation, and Free-tier simulation are
out of scope.

## What Changes

- Add **Simulator Service** (`services/simulator/`, port **8007**) as a
  FastAPI microservice. A **simple decision tree** still picks **3–5
  leaves** (optimistic, baseline, pessimistic, plus up to two extras) with
  a node `trace`. **Qwen3.5-4B** then reasons over those leaves, the
  question, and RAG context and writes each scenario's title, outcome, and
  `assumptions[]`. Monte Carlo and stochastic search stay forbidden.
  Decoding is temperature 0. A retry with the same `X-Request-ID` returns
  the stored run and does not call the model again.
- Pull missing variables via RAG HTTP (`user_id` + `X-Request-ID`). The LLM
  may also read that context when inferring a missing number; any default
  or missing fact becomes an explicit assumption (“no personal sleep data
  found; used default 7h”).
- If the LLM Service returns 5xx or times out, the simulate call is
  **502/504** and nothing is persisted. Template-only success is not a
  valid simulate.
- Persist every run in MongoDB collection `simulations`, isolated by
  `user_id`, so Frame 7 can show history and the thesis can audit traces.
- Register MCP tool **`simulate_whatif`** on Agents Service (`GET /mcp/tools`
  lists it; `POST /mcp/tools/simulate_whatif` wraps Simulator HTTP). The
  Frame 5 `reason_graph` is **not** rewritten: chat does not auto-route
  what-if. Clients (and later agent nodes) invoke the tool explicitly.
- API Router (premium only):
  - `POST /api/simulate` → HTTP sync → Simulator → **200** (not Kafka/202)
  - `GET /api/simulations` and `GET /api/simulations/{id}` (own rows only)
- Rate limit `POST /api/simulate` at **10 req/min** (aligned with upload:
  heavier than chat, cheaper than fine-tune). Correlation ID on every hop.
- Docker Compose: register `simulator-service` next to Agents/RAG.
- Out of scope: Monte Carlo, stochastic search, Free-tier simulator,
  OAuth calendars, voice, social sharing of scenarios.

## Capabilities

### New Capabilities
- `simulator-service`: what-if engine (decision tree of 3–5 leaves, LLM
  reasoning for outcomes and assumptions, RAG-backed variables, MongoDB
  persistence, premium-only HTTP API).

### Modified Capabilities
- `agents-service`: register MCP tool `simulate_whatif` wrapping Simulator
  HTTP; unknown-tool 404 behaviour unchanged.
- `api-router`: new premium simulate/list/get routes; 401/403/404/429
  consistent with existing gateway rules.

## Output

```
openspec/changes/objective-6-decision-support/
├── output/
│   ├── diagrams/
│   │   ├── simulator-architecture.drawio
│   │   ├── simulator-dataflow.drawio
│   │   └── README.md
│   └── documents/
│       └── justificacion-ejemplo.md
├── proposal.md
├── design.md
├── tasks.md
└── specs/
    ├── simulator-service/spec.md
    ├── agents-service/spec.md
    └── api-router/spec.md
```

## Impact

- New service: `services/simulator/` (FastAPI, Dockerfile, port 8007).
  Placeholder package already exists from Frame 1; this frame fills it.
- New MongoDB collection `simulations` (filter `user_id`; unique
  `correlation_id` for idempotent retries of the same request).
- API Router: new routes + `SIMULATOR_SERVICE_URL` + rate-limit bucket.
- Agents Service: one extra MCP tool definition and HTTP handler; no
  change to `reason_graph` / `learn_graph`.
- RAG: consumed as-is (`GET /search`); no RAG requirement change.
- Kafka: **unchanged** (simulate is sync HTTP, like premium chat).
- Downstream: Frame 7 reads `simulations` / list endpoint for the
  dashboard. Frame 8 is parallel and independent.
- Docker Compose: `simulator-service` on 8007; `LLM_SERVICE_URL` points at
  the Frame 4 container.
- Out of scope: Monte Carlo, Free tier, AWS, loading Qwen weights inside
  the simulator process.

## Execution Order

1. Simulator Service skeleton (config, health, correlation ID, Dockerfile).
2. Decision-tree engine (always 3–5 leaves and traces) plus LLM client
   (`POST /chat`, temperature 0) that authors each scenario.
3. RAG variable hydration + MongoDB `simulations` persistence + isolation.
4. MCP `simulate_whatif` on Agents; API Router premium routes + rate limit.
5. Tests (mocked RAG, tree determinism, 403/404/401).
6. `output/` diagrams and justificacion with structured-log examples.
