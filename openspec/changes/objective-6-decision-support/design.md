## Context

See proposal.md — Why. Premium chat already goes API Router → Agents
`reason_graph` → RAG + LLM (30s). RAG Top-k is available over HTTP. There is
no what-if engine, no scenario trace, and no `simulations` collection. Frame 6
adds Simulator Service on port **8007** as a sibling of RAG/Agents.

Constraints from `context.txt`: deterministic what-if with a simple decision
tree; 3–5 scenarios with explicit assumptions; Kafka only for heavy/async
work (simulate is sync); correlation id on every hop; data isolated by
`user_id`; Monte Carlo and stochastic optimisation out of scope; Free tier
has no files and no RAG context; clients never call backend ports; MCP tools
wrap internal HTTP (`simulate_whatif` is the Frame 6 tool). Frame 6 depends
on Frame 1.1 and Frame 3 and may run in parallel with Frame 8.

## Goals / Non-Goals

**Goals:**
- One new microservice that owns the decision tree and the LLM scenario call.
- Always 3–5 scenarios, each with LLM-written assumptions + node trace.
- Hydrate missing variables from RAG HTTP; never open Chroma/GridFS.
- Call LLM Service `POST /chat` (Qwen3.5-4B base, temperature 0) once per new simulate.
- Persist runs for Frame 7 history.
- Register `simulate_whatif` on the existing Agents MCP host.
- Router facade: `POST /api/simulate`, list/get; 10 req/min.

**Non-Goals:**
- Do not load Qwen weights inside the simulator (HTTP to port 8003 only).
- Do not add Monte Carlo, random seeds, or stochastic search.
- Do not return a successful simulate that skipped the LLM.
- Do not rewrite `reason_graph` / `learn_graph` or auto-detect what-if in chat.
- Do not put tree logic inside API Router or Agents Service.
- Do not give Free-tier users simulations.
- Do not use Kafka for simulate (not a heavy async job).

## Decisions

### 1. Dedicated Simulator Service (port 8007)

**Decision**: New FastAPI service `services/simulator/` on port 8007 (8005 is
Chroma, 8006 is Agents). Fill the Frame 1 placeholder package.

**Alternatives considered**:
- Tree inside API Router — rejected (Router must stay a facade).
- Tree inside Agents / new LangGraph — rejected (Frame 6 is parallel with
  Frame 8 and must work if Agents is down; chat must not pay tree latency).
- Tree inside RAG — rejected (RAG is retrieval, not decision support).

**Rationale**: Same microservice pattern as ETL/RAG/LLM: own Dockerfile,
health, and scale profile. Thesis “módulo de valor” is a visible container.

### 2. Decision tree selects leaves; the LLM reasons about them

**Decision**: Encode a small static tree over four variable families:

| Family | Example variables | Defaults if RAG empty |
|--------|-------------------|------------------------|
| Sleep | `sleep_hours` | 7.0 |
| Time | `meeting_hours_per_day`, `focus_hours_per_day` | 3.0 / 4.0 |
| Money | `monthly_spend` | 0 (assumption: unknown) |
| Health | `active_prescriptions` (count) | 0 |

Walk **three mandatory leaves** (optimistic / baseline / pessimistic) plus
up to **two extra leaves** when more than one family is present. Cap at 5.
`trace` is the list of node ids (`sleep_lt_7` → `leaf:fatigue_high`).

Then **one** HTTP call to LLM Service `POST /chat` (Qwen3.5-4B base,
temperature 0) with the question, variables, RAG excerpts, and the leaf
ids. The model returns JSON: one object per leaf with `title`, `outcome`,
and `assumptions`. The service rejects a simulate that did not call the
LLM. Invalid JSON is retried once; a second failure is 502 and no persist.

**Alternatives considered**:
- Fixed English templates and no LLM — rejected (the value module must
  reason about the user's situation, not fill blanks).
- LLM with no tree — rejected (`context.txt` requires a simple decision
  tree and 3–5 explicit scenarios).
- Monte Carlo over variable ranges — rejected (`context.txt` non-goal).

**Rationale**: The tree keeps the academic contract auditable. The LLM
does the inference the thesis asks of every value module. Temperature 0
and a stored `correlation_id` keep retries stable.

### 3. RAG hydration only when variables are missing

**Decision**: If the client sends a complete `variables` object for the
detected families, skip RAG. Otherwise `GET` RAG `/search` with the question
and parse numbers with conservative regex/heuristics. RAG 5xx/timeout while
hydration is required → 502/504 and **no** persist. If RAG 200 with zero
hits, apply defaults and record the assumption.

**Alternatives considered**: Always call RAG — rejected (wastes the 30s
budget when the UI already has diary numbers from Frame 7).

### 4. Sync HTTP, not Kafka

**Decision**: `POST /api/simulate` waits for the tree plus one LLM call
(30s budget, same as premium chat) and returns 200. No `task_status`, no
polling. LLM 5xx or timeout → 502/504, no persist.

**Rationale**: One inference hop fits the sync chat budget. Kafka stays
for upload/ETL/learn_graph.

### 5. Idempotent persist on `correlation_id`

**Decision**: Unique index on `simulations.correlation_id`. Retry with the
same `X-Request-ID` returns the stored document.

### 6. MCP tool without changing chat graphs

**Decision**: Add `simulate_whatif` to the Agents registry. Handler is HTTP
to Simulator `POST /simulate`. `reason_graph` stays retrieve → generate →
assumptions. UI and tests call Router; agents call the tool explicitly.

**Alternatives considered**: Intent classifier node on chat — rejected
(changes Frame 5 latency and acceptance tests; not required by OE6).

### 7. Router stays the only client-facing entry

**Decision**: Clients never call port 8007. Router validates JWT and tier,
then HTTP to Simulator. List/get are proxied the same way.

## Data Flow

### Premium simulate (sync)

```
1. Client POST /api/simulate {question, variables?}
2. API Router: JWT ✓, tier=premium, rate-limit 10/min, X-Request-ID
3. Router HTTP POST simulator-service:8007/simulate
4. If correlation_id exists → return stored document (idempotent)
5. If variables incomplete → HTTP GET RAG 8002 /search (user_id)
6. Parse or default variables; collect sources
7. Walk decision tree → 3–5 leaf ids + traces
8. HTTP POST LLM 8003 /chat (temperature 0) → scenario text + assumptions
9. Upsert MongoDB simulations
10. HTTP 200 {simulation_id, scenario_count, scenarios, assumptions, sources, llm_used}
    (no Kafka)
```

### List / get

```
1. Client GET /api/simulations[/{id}]
2. Router: JWT ✓, premium
3. Simulator GET /simulations filtered by user_id
4. Cross-user id → 404
```

### MCP tool (optional agent path)

```
1. POST agents:8006/mcp/tools/simulate_whatif
2. Agents HTTP POST simulator:8007/simulate (same X-Request-ID)
3. 502/504 if Simulator fails; unknown tool name → 404
```

### Free / errors

```
Free POST /api/simulate     → 403 (no Simulator call)
No JWT                      → 401
Blank question              → 422
11th simulate in a minute   → 429
RAG 5xx while hydrating     → 502/504, no persist
LLM 5xx / timeout / bad JSON → 502/504, no persist
```

## Configuration

```
SIMULATOR_HOST=0.0.0.0
SIMULATOR_PORT=8007
RAG_SERVICE_URL=http://rag-service:8002
LLM_SERVICE_URL=http://llm-service:8003
LLM_TEMPERATURE=0
MONGODB_URI=...
MONGODB_DB=llm_brain
DEFAULT_SLEEP_HOURS=7
DEFAULT_MEETING_HOURS=3
DEFAULT_FOCUS_HOURS=4
```

Router: `SIMULATOR_SERVICE_URL=http://simulator-service:8007`
Agents: `SIMULATOR_SERVICE_URL=http://simulator-service:8007`
Rate limit: `RATE_LIMIT_SIMULATE=10`

## Data model (MongoDB)

```
simulations:
  { _id, user_id, correlation_id (unique),
    question, variables{}, sources[],
    scenarios: [{ id, title, outcome, assumptions[], trace[], severity }],
    scenario_count, llm_used, model_id, created_at }
```

All queries filter `user_id`. Unique index on `correlation_id`.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Tree too naive alone | LLM writes the outcome; the tree only chooses which 3–5 futures exist |
| LLM prose varies across calls | Temperature 0; same `X-Request-ID` returns the stored document |
| LLM JSON is malformed | One retry, then 502 and no persist |
| RAG + LLM exceed 30s | 504; client retries with the same correlation id |
| Heuristic RAG parse is brittle | Defaults + explicit “no personal context” assumption; the LLM also sees the raw excerpts |
| Duplicate retries create two rows | Unique `correlation_id` |
| Agents down vs UI | UI uses Router → Simulator; MCP is additive |

## Migration Plan

1. Deploy Simulator Service via Docker Compose (local MVP).
2. Add Router routes and Agents tool; no flag needed (new endpoints).
3. Rollback: stop the container; Router maps Simulator 502; existing chat
   unchanged.

## Open Questions

None that block specs or tasks. Extra tree families (nutrition, travel) can
wait; the four families above cover sleep/productivity, meetings/focus,
invoices, and prescriptions already in the sample corpus.

## Design Patterns & SOLID Principles

### Patterns Used

| Pattern | Where | Purpose |
|---------|-------|---------|
| **Decision tree** | Simulator engine | Choose 3–5 leaves and a trace |
| **Interpreter** | LLM `POST /chat` | Reason about each leaf in the user's context |
| **Facade** | API Router | Clients never address port 8007 |
| **Protocol (MCP tools)** | `simulate_whatif` | Same contract as Frame 5 tools |
| **Idempotent command** | `correlation_id` unique index | Safe client retries |
| **Gateway routing** | Premium vs Free | Tier isolation at the edge |
| **Anti-corruption (HTTP)** | RAG client | No Chroma types leak into the tree |

### SOLID Principles Applied

| Principle | Application |
|-----------|-------------|
| **S** | Engine walks the tree; LLM client reasons; RAG client hydrates; repository persists |
| **O** | New leaf/family without changing FastAPI routes |
| **L** | Any variable provider (body vs RAG vs defaults) yields the same dict |
| **I** | Separate `/simulate` vs `/simulations` vs MCP tool |
| **D** | Engine depends on RAG and LLM URLs, not Chroma or model weights |
