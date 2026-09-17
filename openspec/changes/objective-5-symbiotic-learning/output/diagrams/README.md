# Frame 5 — Symbiotic Learning Architecture Diagrams

Draw.io XML for the Agents Service (LangGraph + MCP tools) that closes the
Brain–LLM loop for premium users.

## Files

| File | What it shows |
|------|----------------|
| `agents-architecture.drawio` | Components. Blue = existing Frame 1–4. Green = this frame. |
| `agents-dataflow.drawio` | Numbered reason_graph + Kafka learn_graph + manual train + error paths. |

## Arrow direction (`agents-architecture.drawio`)

Solid = call / write. Dashed = HTTP 200/202 response.

| From | To | Meaning |
|------|----|---------|
| Client | API Router :8000 | `POST /api/chat`, `POST /api/sessions/end`, `POST /api/finetune` + JWT |
| API Router | Client | **200** (chat) / **202** (session-end, finetune) — dashed |
| API Router | Agents :8006 | Premium **POST /reason** (Razonador). Clients never call :8006 |
| Agents | API Router | **200** `{response, assumptions, sources}` — dashed |
| API Router | Kafka | **after 200**: publish `session.turn.completed` (same `X-Request-ID`) |
| Kafka | `learn_graph` | consume → ingest → evaluate → maybe_append_batch |
| FastAPI :8006 | `reason_graph` | `reason_graph.invoke` (sync chat path) |
| `reason_graph` | Razonador | retrieve + generate + assumptions nodes |
| Razonador / graphs | MCP registry | tools are the only way to reach RAG/LLM/Fine-Tune |
| MCP `rag_search` | RAG :8002 | HTTP **GET /search** with `user_id` + `X-Request-ID` |
| RAG :8002 | MCP | context + sources — dashed |
| MCP `llm_generate` | LLM :8003 | HTTP **POST /chat** (Qwen3.5-4B base container) |
| LLM :8003 | MCP | answer + `tokens_used` — dashed |
| Ingestor | MongoDB | upsert `agent_interactions` (unique `correlation_id`) |
| Evaluador | MongoDB | `agent_feedback` + `finetune_batches` — **no** `/train` |
| Evaluador | weekly batch box | status `accumulating` / `ready` |
| API Router | Agents :8006 | **POST /batches/{id}/trigger** (manual) |
| MCP `finetune_trigger` | Fine-Tune :8004 | HTTP **POST /train** (local LoRA) — **only** this arrow trains |
| Fine-Tune :8004 | MCP | **202** `job_id` — dashed |

There is **no** arrow from the client into Agents :8006. There is **no** arrow from Evaluador / `learn_graph` into Fine-Tune. There is **no** Premium chat arrow from Router directly to RAG or LLM (unless `CHAT_VIA_AGENTS=false` rollback). LangChain stays inside RAG :8002.

## Arrow direction (`agents-dataflow.drawio`)

### Flow 1 — `reason_graph` (sync)

1. Client → API Router `POST /api/chat` (JWT premium).
2. Router → Agents `POST /reason` → `reason_graph.invoke`.
3. `retrieve_context` → `rag_search` → RAG :8002.
4. `generate_answer` → `llm_generate` → LLM `POST /chat`.
5. `extract_assumptions` (empty RAG must include “no personal context”).
6. **200** `{response, assumptions, sources}` dashed back to the client **before** Kafka.

### Flow 2 — Kafka `learn_graph` (async)

1. Router **after 200** → Kafka `session.turn.completed`.
2. Consumer → `ingest_turn` (idempotent upsert).
3. `evaluate_turn` writes `agent_feedback` (heuristic, no extra LLM).
4. `maybe_append_batch` updates `(user_id, ISO week)` to `accumulating` / `ready`.
5. Red “NO POST /train” callout: Evaluador never points at Fine-Tune.

### Flow 3 — Manual train

1. Client `POST /api/finetune {batch_id}` → Router (422 if `batch_id` missing).
2. Agents `POST /batches/{id}/trigger`.
3. Ready gate: empty / not `ready` / already `submitted` → **409**, no `/train`.
4. Export JSONL `dataset_path` → Fine-Tune `POST /train`.
5. **202** `{job_id}`, batch `status=submitted`, dashed back to the client.

### Flow 4 — Errors (red)

Every red box has an incoming arrow from the step that produces it.

| From | To | Meaning |
|------|----|---------|
| `generate_answer` (step 5) | LLM 5xx / timeout | **502** / **504**; no ingest, no Kafka |
| API Router (Flow 1 step 2) | Free tier chat | skip Agents, no RAG, no Kafka |
| `POST /reason` (step 3) | Free `/reason` or `/sessions/end` | HTTP **403** |
| Agents trigger (Flow 3 step 3) | Cross-user batch / interaction | HTTP **404** (no leak) |
| `POST /reason` / Agents host (step 3) | Unknown MCP tool | `POST /mcp/tools/{name}` → **404** |
| Ready? gate (Flow 3 step 4) | Trigger not ready / empty / submitted | HTTP **409**; no Fine-Tune call |
| API Router (Flow 1 step 2) | No JWT on `/api/chat` | HTTP **401**; no Agents call |

## Color scheme

- Blue (`#dae8fc`): Router, Kafka, client, LLM, Fine-Tune, RAG (existing)
- Green (`#d5e8d4`): Agents Service, graphs, MCP tools, 202 job_id
- Yellow (`#fff2cc`): assumptions diamond, JSONL export, ready gate, correlation notes
- Gray (`#f5f5f5`): MongoDB collections
- Red (`#f8cecc`): forbidden / error paths (no auto-train, Free skip, 403/404/409)

## How to open

Draw.io desktop, [app.diagrams.net](https://app.diagrams.net), or the VS Code Draw.io extension.

## References

- [Frame 1 diagrams](../../objective-1-0-architecture-repo/output/diagrams/)
- [Frame 1.1 API Router](../../objective-1-1-api-router/output/diagrams/)
- [Frame 3 RAG diagrams](../../objective-3-hybrid-store-rag/output/diagrams/)
- [Frame 4 LLM / Fine-Tune](../../objective-4-llm-inference-finetuning/output/)
