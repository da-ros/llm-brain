## Context

See proposal.md — Why. Premium chat today is API Router → RAG (8002) → LLM (8003)
over HTTP sync (30s). ETL (8001) and Fine-Tune (8004) are already separate
services. There is no session memory of *reasoning*, no assumption log, and no
weekly batch for manual LoRA. Frame 5 adds Agents Service on port **8006** that
orchestrates Ingestor / Razonador / Evaluador with **LangGraph** and leaves ETL,
RAG, and Bedrock in place.

Constraints from `context.txt`: Kafka for heavy/async work, HTTP for chat;
correlation id on every hop; data isolated by `user_id`; fine-tuning is
**manual** (agent or admin trigger), never real-time auto-retrain; Free tier
has no files and no RAG context. LangChain is already the RAG library (Frame 3);
it is not reused as the agent runtime.

## Goals / Non-Goals

**Goals:**
- One new microservice that hosts three MCP agents as LangGraph nodes.
- Two compiled graphs: `reason_graph` (sync chat) and `learn_graph` (async Kafka).
- Premium chat answers come from Razonador (RAG + LLM + assumptions).
- Ingestor + Evaluador run **after** the HTTP response (Kafka), so chat stays
  within 30s.
- Weekly batch in MongoDB; `POST /train` only on explicit trigger.
- Same observability as other services (`X-Request-ID`, structured logs).

**Non-Goals:**
- Do not use LangChain `AgentExecutor` / ReAct agents as the loop runtime.
- Do not call Bedrock or Chroma from Agents Service (HTTP to existing services).
- Do not embed agent logic inside API Router, RAG, or LLM services.
- Do not run a full MCP stdio subprocess per agent (overkill for MVP).
- Do not auto-submit Bedrock jobs.
- Do not give Free-tier users the loop (no context, no files).
- Do not implement RLHF, multi-agent debate, or Monte Carlo.

## Decisions

### 1. Dedicated Agents Service (port 8006)

**Decision**: New FastAPI service `services/agents/` on port 8006 (8005 is Chroma).

**Alternatives considered**:
- Agents inside API Router — rejected (Router must stay a facade).
- Agents inside LLM Service — rejected (LLM is inference-only).

**Rationale**: Frame 5 *integrates* 2+3+4; a sibling service matches the existing
microservice pattern (own Dockerfile, own health, independent scale).

### 2. LangGraph for the loop, LangChain for RAG only

**Decision**: Orchestrate Frame 5 with **LangGraph** (`StateGraph`). Keep
**LangChain** in the RAG service (retriever, text splitters). Agent nodes call
RAG / LLM / Fine-Tune over HTTP (`httpx`); they do not construct LangChain
chains against Bedrock.

**Why LangGraph (not LangChain agents):**

| Need in Frame 5 | LangChain LCEL / AgentExecutor | LangGraph |
|-----------------|--------------------------------|-----------|
| Three specialized agents with a host | Possible but ad-hoc | Native nodes + shared typed state |
| Conditional paths (empty RAG, LLM 5xx, score threshold) | Awkward branching | Conditional edges |
| Sync reason vs async learn as two pipelines | Two unrelated chains | Two compiled graphs, same state vocabulary |
| Traceable assumptions on the turn | Prompt-only | State fields + node outputs |
| Thesis “IA agéntica” architecture | Legacy agent API | Current standard for agent graphs |

LangChain alone would be enough for “retrieve then generate”. The *symbiotic loop*
is a state machine (reason → ingest → evaluate → maybe batch). That is LangGraph.

**Alternatives considered**:
- LangChain `AgentExecutor` + tools — rejected (unstructured control flow,
  weaker story for three named agents, library is being superseded for agents).
- Custom Python if/else with no graph — rejected (harder to diagram, test edges,
  and defend as agentic architecture).
- CrewAI / AutoGen — rejected (extra stack, multi-agent debate is out of scope).

**Rationale**: LangGraph sits on `langchain-core`, stays OSS, and maps 1:1 to the
C4/MCP diagrams for the defense. RAG does not need to change.

### 3. Two compiled graphs, not one giant cycle

**Decision**:

`reason_graph` (invoked by `POST /reason`, counts toward 30s):

```
START → retrieve_context → generate_answer → extract_assumptions → END
                              │
                              └─ on LLM 5xx/timeout → error END (no ingest)
```

`learn_graph` (invoked by Kafka `session.turn.completed`):

```
START → ingest_turn → evaluate_turn → maybe_append_batch → END
```

Typed state (shared fields, two TypedDicts): `user_id`, `session_id`,
`correlation_id`, `messages`/`query`, `context`, `sources`, `response`,
`assumptions`, `tokens_used`, `score`, `should_include_in_batch`, `error`.

**Alternatives considered**: One graph that includes ingest on the request path —
rejected (evaluation must not add chat latency).

### 4. MCP as tool contracts over HTTP, graphs as the implementation

**Decision**: `GET /mcp/tools` lists `reason`, `ingest_turn`, `evaluate_turn`.
`POST /mcp/tools/{name}` maps to `reason_graph.invoke` or `learn_graph` nodes.
FastAPI `POST /reason` is a facade over the same `reason` tool.

**Alternatives considered**: Official MCP SDK + stdio — rejected for MVP.

**Rationale**: MCP remains the *contract* (what each agent exposes). LangGraph is
the *runtime* (how the loop runs).

### 5. New Kafka topic `session.turn.completed`

**Decision**: Router publishes after a successful premium Razonador response.
Payload is metadata + texts (not files). Existing `file.uploaded` /
`task.response` stay as they are.

**Alternatives considered**: Reuse `task.response` — rejected (ETL contract).

### 6. Scoring heuristic, not a second LLM judge

**Decision**: Evaluador node uses deterministic heuristics (non-empty answer,
presence of assumptions) plus `EVAL_SCORE_THRESHOLD`. No extra Bedrock call.

### 7. Weekly batch identity

**Decision**: One `finetune_batches` document per `(user_id, ISO week)`. Status
`accumulating` → `ready` → `submitted`. Trigger calls Fine-Tune `POST /train`.

### 8. Router stays the only client-facing entry

**Decision**: Clients never call port 8006. Router validates JWT and tier, then
HTTP to Agents Service.

## Data Flow

### Premium chat turn (sync + async)

```
1. Client POST /api/chat {message, session_id?}
2. API Router: JWT ✓, tier=premium, X-Request-ID
3. Router HTTP POST agents-service:8006/reason
4. reason_graph.invoke(state):
      retrieve_context  → HTTP RAG (user_id)
      generate_answer   → HTTP LLM /chat
      extract_assumptions
5. Router: HTTP 200 {response, assumptions, sources, tokens_used, session_id}
6. Router: publish Kafka session.turn.completed
7. learn_graph.invoke(state):
      ingest_turn          → upsert agent_interactions
      evaluate_turn        → agent_feedback (never POST /train)
      maybe_append_batch   → finetune_batches
```

### Session end (async)

```
1. Client POST /api/sessions/end {session_id}
2. Router: JWT ✓, premium → 202
3. Notify Evaluador to finalize session feedback
```

### Manual fine-tune (async hours)

```
1. Client POST /api/finetune {batch_id}
2. Router → Agents POST /batches/{id}/trigger
3. Ready only; else 409
4. HTTP Fine-Tune POST /train
5. Batch status=submitted; return job_id
```

### Free chat

```
1. POST /api/chat → Router
2. No Agents, no LangGraph, no RAG, no session.turn.completed
3. On-device LLM is Frame 10
```

## Configuration

```
AGENTS_HOST=0.0.0.0
AGENTS_PORT=8006
RAG_SERVICE_URL=http://rag-service:8002
LLM_SERVICE_URL=http://llm-service:8003
FINETUNE_SERVICE_URL=http://finetune-service:8004
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_TOPIC_SESSION_TURN=session.turn.completed
EVAL_SCORE_THRESHOLD=0.6
BATCH_MIN_ITEMS=10
MONGODB_URI=...
```

## Data model (MongoDB)

```
agent_interactions:
  { _id, user_id, session_id, correlation_id (unique),
    query, response, assumptions[], sources[], created_at }

agent_feedback:
  { _id, user_id, correlation_id, session_id,
    score, reason, should_include_in_batch, created_at }

finetune_batches:
  { _id, user_id, iso_week, items[], status,
    dataset_path?, job_id?, created_at, updated_at }
```

All queries filter `user_id`. Unique index on `agent_interactions.correlation_id`.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Chat latency (RAG + LLM already tight on 30s) | Only `reason_graph` on the request; `learn_graph` after 200 |
| LangGraph adds a dependency | `langgraph` is OSS; RAG keeps LangChain; no Bedrock in this service |
| Graph overkill for three nodes | Two small graphs are still easier to test and diagram than ad-hoc if/else |
| Kafka topic not in original context diagram | Documented as Frame 5 addition in `context.txt` |
| Heuristic scores are crude | Threshold + manual review of `ready` batches |
| Duplicate Kafka deliveries | Idempotent ingest on `correlation_id` |
| Agents Service as extra SPOF for premium chat | Health check; Router maps 502/504 |

## Migration Plan

1. Deploy Agents Service beside existing stack (Compose / ECS).
2. Switch premium chat route in API Router behind `CHAT_VIA_AGENTS=true`.
3. Rollback: flag false → previous Router→RAG→LLM path; Kafka consumer can idle.

## Open Questions

None that block specs or tasks. LangGraph checkpointer (thread_id = correlation_id)
can be added later for replay; MVP can run graphs without a durable checkpointer
because MongoDB already stores the turn.

## Design Patterns & SOLID Principles

### Patterns Used

| Pattern | Where | Purpose |
|---------|-------|---------|
| **State machine (LangGraph)** | `reason_graph`, `learn_graph` | Explicit control flow and typed turn state |
| **Facade** | API Router | Clients never address port 8006 |
| **Strategy** | Ingestor / Razonador / Evaluador nodes | Same state, different node functions |
| **Protocol (MCP tools)** | `/mcp/tools` | Formalize what each agent exposes |
| **Producer/Consumer** | `session.turn.completed` | Decouple chat 200 from `learn_graph` |
| **Idempotent consumer** | Ingestor node | Safe Kafka at-least-once |
| **Gateway routing** | Premium vs Free chat | Tier isolation at the edge |

### SOLID Principles Applied

| Principle | Application |
|-----------|-------------|
| **S** | Each graph node does one step; Fine-Tune still trains |
| **O** | New node/edge without rewriting FastAPI routes |
| **L** | Any node that reads/writes the TypedDict can sit on the graph |
| **I** | Separate tools (`reason` vs `ingest_turn` vs `evaluate_turn`) |
| **D** | Nodes depend on RAG/LLM/Fine-Tune HTTP URLs, not internals |
