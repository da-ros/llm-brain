## Why

> **Current runtime.** This file keeps the decision text of this frame. Before citing it as the running system, read `docs/architecture/current-runtime.md`.


Frames 2–4 already store personal documents, retrieve them with RAG, and generate
answers with the local Qwen3.5-4B LLM container, but they do not close the Brain–LLM
loop: interactions are
not ingested as memory, reasoning is not recorded with explicit assumptions, and
nothing prepares a weekly fine-tuning batch. Frame 5 adds the symbiotic learning
loop so the platform can co-evolve with each premium user without auto-retraining
in real time.

## Context from Frame 2, 3 and 4

- **Frame 2 (ETL, port 8001)**: Kafka consumer on `file.uploaded`; produces JSONL
  triples tagged with `user_id`; publishes `task.response`.
- **Frame 3 (RAG, port 8002)**: MongoDB + Chroma, Fernet-encrypted embeddings,
  Top-k retrieval scoped by `user_id`; HTTP sync used by chat.
- **Frame 4 (LLM port 8003, Fine-Tune port 8004)**: multimodal Qwen3.5-4B inference
  as a host process on port 8003 for premium users; local LoRA (PEFT/ms-swift) jobs
  submitted only by explicit `POST /train` (manual, not automatic).
- **Frame 1.1 (API Router, port 8000)**: JWT, `X-Request-ID`, `POST /api/chat`
  currently calls RAG then LLM directly.

Frame 5 **integrates** those three services. It does not replace ETL, RAG, or the
local Qwen3.5-4B LLM Service.

## What Changes

- Add **Agents Service** (`services/agents/`, port **8006**) as a FastAPI microservice
  that orchestrates three MCP agents (**Ingestor**, **Razonador**, **Evaluador**) with
  **LangGraph** state graphs. We implement our **own MCP tool contracts** (no
  third-party MCP servers — keeps it local and $0): `rag_search` (RAG 8002),
  `llm_generate` (LLM 8003, Qwen3.5-4B), `ingest_turn` (MongoDB `agent_interactions`),
  `evaluate_turn` (MongoDB `agent_feedback`, `finetune_batches`), and `finetune_trigger`
  (Fine-Tune 8004, manual only). LangGraph nodes invoke these tools over HTTP.
  LangChain remains the RAG stack (Frame 3); it is not the agent runtime.
- **Premium chat routing** (**BREAKING** for premium only): `POST /api/chat` calls
  Razonador instead of RAG+LLM directly. Razonador retrieves context (RAG), generates
  the answer (LLM), and records explicit assumptions. Free-tier chat is unchanged
  (on-device, Frame 10 — no context, no files, no agents).
- After each premium chat turn, the Router publishes Kafka topic `session.turn.completed`
  (async). Ingestor persists the interaction; Evaluador writes feedback and appends
  eligible samples to the user's weekly fine-tune batch.
- Add Router endpoints to list ready batches and to **manually** trigger Fine-Tune
  Service (`POST /api/finetune`). Evaluador never starts training by itself.
- Add MongoDB collections `agent_interactions`, `agent_feedback`, `finetune_batches`,
  always isolated by `user_id`.
- Correlation ID (`X-Request-ID`) and structured logging on every agent hop.

## Capabilities

### New Capabilities
- `agents-service`: LangGraph-orchestrated MCP agents (Ingestor, Razonador,
  Evaluador), session ingestion, assumption-traced reasoning, weekly fine-tune
  batch preparation, and manual training trigger — premium users only.

### Modified Capabilities
- `api-router`: Premium `POST /api/chat` routes through Razonador; new session-turn
  Kafka event; new `POST /api/sessions/end` and `POST /api/finetune` (manual).

## Output

```
openspec/changes/objective-5-symbiotic-learning/
├── output/
│   ├── diagrams/
│   │   ├── agents-architecture.drawio
│   │   ├── agents-dataflow.drawio
│   │   └── README.md
│   └── documents/
│       └── justificacion-ejemplo.md
├── proposal.md
├── design.md
├── tasks.md
└── specs/
    ├── agents-service/spec.md
    └── api-router/spec.md
```

## Impact

- New service: `services/agents/` (FastAPI + LangGraph, Dockerfile, port 8006).
- New dependency: `langgraph` (orchestration). Agents call RAG/LLM/Fine-Tune over
  HTTP via their own MCP tools; they do not embed the LLM weights (Qwen3.5-4B),
  Chroma, or LangChain retrievers.
- API Router: chat router for premium; Kafka producer `session.turn.completed`;
  new routes for session end and manual fine-tune.
- Kafka: new topic `session.turn.completed` (payload: correlation_id, user_id,
  session_id, query, response, assumptions). Existing `file.uploaded` /
  `task.response` unchanged.
- MongoDB: three new collections, TTL aligned with `TASK_STATUS_TTL_DAYS` for
  feedback logs; batches persist until consumed.
- Downstream: Fine-Tune Service `POST /train` is called only after an authenticated
  manual trigger with a batch produced by Evaluador.
- Docker Compose: register `agents-service` next to ETL/RAG/LLM.
- Out of scope: real-time auto-retraining, RLHF, multi-agent debate, free-tier
  agents, social sharing of memory.

## Execution Order

1. Agents Service skeleton (config, health, correlation ID, Dockerfile).
2. LangGraph `reason_graph` + `learn_graph`, MCP tool contracts, Ingestor /
   Razonador / Evaluador nodes.
3. Kafka consumer for `session.turn.completed`.
4. API Router: premium chat → Razonador; session-end; manual fine-tune.
5. Tests (mocked RAG, LLM, Kafka, MongoDB).
6. `output/` diagrams and justificacion with structured-log examples.
