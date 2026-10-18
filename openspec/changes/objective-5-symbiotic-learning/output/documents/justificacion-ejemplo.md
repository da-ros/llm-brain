# Justificación — Symbiotic Learning Loop (Frame 5)

El Agents Service (puerto **8006**) cierra el ciclo Brain–LLM para usuarios
**Premium**: Razonador responde con RAG + Qwen3.5-4B y asunciones explícitas;
Ingestor y Evaluador corren **después** del HTTP 200 vía Kafka; el fine-tune
LoRA local solo arranca con un trigger humano.

Los stubs vacíos `ingestor.py` / `razonador.py` / `evaluador.py` no implementaban
el loop. Esta entrega los sustituye por grafos LangGraph, contratos MCP propios
y la integración en el API Router.

---

## Por qué LangGraph (y no LangChain agents)

LangChain **ya** es el runtime de RAG (Frame 3: splitter, retriever). Reutilizar
`AgentExecutor` / ReAct para el loop simbiótico mezclaría dos problemas distintos
y dejaría el control flow (RAG vacío, LLM 5xx, umbral de score, batch semanal)
como `if/else` opaco.

| Necesidad Frame 5 | LangChain LCEL / AgentExecutor | LangGraph |
|-------------------|--------------------------------|-----------|
| Tres agentes con host (Ingestor, Razonador, Evaluador) | Ad-hoc | Nodos + estado tipado |
| Caminos condicionales (RAG vacío, LLM 5xx, umbral) | Branching incómodo | Conditional edges |
| Chat sync vs aprendizaje async | Dos chains sueltas | `reason_graph` + `learn_graph` |
| Asunciones trazables | Solo en el prompt | Campos de estado + salida del nodo |
| Tesis “IA agéntica” | API legado de agents | Estándar actual de grafos |

`POST /reason` es una fachada sobre `reason_graph.invoke`. El consumer Kafka
invoca `learn_graph.invoke`. Los nodos **no** cargan pesos de Qwen3.5-4B ni
hablan con Chroma: llaman herramientas MCP HTTP.

---

## Contratos MCP propios (sin servidores de terceros)

`GET /mcp/tools` lista el registro. `POST /mcp/tools/{name}` invoca; nombre
desconocido → **404**.

| Tool | Dueño | Envuelve |
|------|-------|----------|
| `rag_search` | Razonador | RAG :8002 `GET /search` |
| `llm_generate` | Razonador | LLM :8003 `POST /chat` |
| `ingest_turn` | Ingestor | MongoDB `agent_interactions` |
| `evaluate_turn` | Evaluador | MongoDB `agent_feedback`, `finetune_batches` |
| `finetune_trigger` | Evaluador (manual) | Fine-Tune :8004 `POST /train` |

---

## Grafos

```
reason_graph (sync, ≤30s)
  START → retrieve_context → generate_answer → extract_assumptions → END
                                └─ LLM 5xx/timeout → error END (sin ingest)

learn_graph (Kafka session.turn.completed)
  START → ingest_turn → evaluate_turn → maybe_append_batch → END
  (nunca POST /train)
```

Evaluador puntúa con heurística (respuesta no vacía + asunciones) y
`EVAL_SCORE_THRESHOLD=0.6`. Un batch por `(user_id, ISO week)`:
`accumulating` → `ready` → `submitted`.

---

## Logging estructurado

Formato (CorrelationFilter):

```
%(asctime)s [%(correlation_id)s] %(levelname)s %(name)s: %(message)s
```

### POST /reason (Razonador)

```
2026-09-16T15:00:00 [abc-123] INFO agents-service: POST /reason user_id=user1 session_id=sess-1
2026-09-16T15:00:00 [abc-123] INFO agents-service: reason_graph.invoke
2026-09-16T15:00:00 [abc-123] INFO agents-service: reason_graph: retrieve_context
2026-09-16T15:00:00 [abc-123] INFO agents-service: MCP rag_search → RAG http://rag-service:8002/search user_id=user1
2026-09-16T15:00:00 [abc-123] INFO agents-service: reason_graph: generate_answer
2026-09-16T15:00:00 [abc-123] INFO agents-service: MCP llm_generate → LLM http://host.docker.internal:8003/chat (Qwen3.5-4B)
2026-09-16T15:00:01 [abc-123] INFO agents-service: reason_graph: extract_assumptions
```

LLM 5xx (no hay ingest ni Kafka):

```
2026-09-16T15:00:01 [abc-123] ERROR agents-service: LLM service HTTP 500
2026-09-16T15:00:01 [abc-123] ERROR agents-service: reason_graph error (upstream): LLM service HTTP 500
```

### Kafka learn_graph

```
2026-09-16T15:00:01 [abc-123] INFO api-gateway: Publishing to Kafka: session.turn.completed
2026-09-16T15:00:01 [abc-123] INFO agents-service: Consumed from Kafka: session.turn.completed
2026-09-16T15:00:01 [abc-123] INFO agents-service: learn_graph.invoke
2026-09-16T15:00:01 [abc-123] INFO agents-service: learn_graph: ingest_turn
2026-09-16T15:00:01 [abc-123] INFO agents-service: MCP ingest_turn → MongoDB agent_interactions
2026-09-16T15:00:01 [abc-123] INFO agents-service: learn_graph: evaluate_turn
2026-09-16T15:00:01 [abc-123] INFO agents-service: MCP evaluate_turn score=1.00 include=True (never POST /train)
2026-09-16T15:00:01 [abc-123] INFO agents-service: learn_graph: maybe_append_batch
2026-09-16T15:00:01 [abc-123] INFO agents-service: MCP evaluate_turn append_batch → MongoDB finetune_batches (no POST /train)
```

### POST /batches/{id}/trigger

```
2026-09-16T16:00:00 [def-456] INFO agents-service: POST /batches/b-ready/trigger user_id=user1
2026-09-16T16:00:00 [def-456] INFO agents-service: MCP finetune_trigger → Fine-Tune http://finetune-service:8004/train
2026-09-16T16:00:00 [def-456] INFO agents-service: Batch b-ready submitted job_id=ft-job-1 dataset=data/finetune_batches/user1/2026-W38.jsonl
```

Batch no listo:

```
2026-09-16T16:00:00 [def-456] INFO agents-service: POST /batches/b-empty/trigger user_id=user1
```

HTTP **409**, sin llamada a Fine-Tune.

### CorrelationFilter

Si el inbound trae `X-Request-ID: abc-123`, ese id viaja a RAG/LLM/Fine-Tune y
aparece en **cada** línea. Si falta, Agents genera un UUID, lo usa en el hop y
lo devuelve en la respuesta (el Router es quien normalmente lo crea).

```
2026-09-16T15:00:00 [abc-123] INFO agents-service: POST /reason
2026-09-16T15:00:00 [no-id]   INFO agents-service: GET /health
```

---

## Patrones

| Pattern | Dónde | Para qué |
|---------|-------|----------|
| **State machine (LangGraph)** | `reason_graph`, `learn_graph` | Control flow explícito y estado del turno |
| **Facade** | API Router | El cliente nunca habla con :8006 |
| **Strategy** | Ingestor / Razonador / Evaluador | Mismo estado, funciones de nodo distintas |
| **Protocol (MCP tools)** | `/mcp/tools` | Qué expone cada agente y qué servicio envuelve |
| **Producer/Consumer** | `session.turn.completed` | Desacoplar el 200 del `learn_graph` |
| **Idempotent consumer** | `ingest_turn` | Kafka at-least-once seguro |
| **Gateway routing** | Premium vs Free | Aislamiento de tier en el borde |

## SOLID

| Principio | Aplicación |
|-----------|------------|
| **S** | Cada nodo hace un paso; Fine-Tune sigue entrenando |
| **O** | Nuevo nodo/edge sin reescribir las rutas FastAPI |
| **L** | Cualquier nodo que lea/escriba el TypedDict puede sentarse en el grafo |
| **I** | Tools separados (`rag_search` vs `ingest_turn` vs `finetune_trigger`) |
| **D** | Nodos dependen de URLs HTTP, no de pesos LLM ni de Chroma |

---

## Errores HTTP

| Caso | Código |
|------|--------|
| Free en `/reason`, `/sessions/end`, `/api/finetune` | 403 |
| Cross-user batch / interaction | 404 |
| Tool MCP desconocido | 404 |
| LLM 5xx / Agents caído | 502 |
| LLM timeout | 504 |
| Batch vacío / no `ready` / ya `submitted` | 409 |
| `POST /api/finetune` sin `batch_id` | 422 |
| Chat sin JWT | 401 |

Rollback: `CHAT_VIA_AGENTS=false` restaura Router → RAG → LLM y deja idle el
consumer Kafka.
