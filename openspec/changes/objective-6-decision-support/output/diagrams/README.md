# Frame 6 — Decision-Support Simulator Diagrams

Draw.io XML for the premium what-if simulator. A decision tree picks 3–5
leaves. Qwen3.5-4B (`POST /chat`, temperature 0) writes each scenario.
The call is synchronous HTTP. Simulate does not publish Kafka.

## Files

| File | What it shows |
|------|----------------|
| `simulator-architecture.drawio` | Components. Blue = Frame 1.1 / 3 / 4 / 5. Green = this frame. |
| `simulator-dataflow.drawio` | Numbered simulate, list/get, MCP, and error paths. |

## Arrow legend

Solid = call or write. The arrowhead sits on the callee.

Dashed = HTTP 200 (or 502/504) response. The arrowhead sits on the caller.

`startArrow` is `none` on every edge. `endArrow` is `classic`. There is no
Kafka shape and no edge whose target is Kafka.

## Arrow direction (`simulator-architecture.drawio`)

| From | To | Line | Meaning |
|------|----|------|---------|
| Client | API Router :8000 | solid | `POST /api/simulate`, `GET /api/simulations` + JWT |
| API Router | Client | dashed | **200** scenarios. Not 202. No Kafka |
| API Router | Simulator :8007 | solid | Premium `POST /simulate` and `GET /simulations`. Clients never call :8007 |
| Simulator | API Router | dashed | **200** `{scenarios, assumptions, llm_used}` |
| Simulator FastAPI | Decision tree | solid | Walk 3–5 leaves and record `trace` |
| Simulator FastAPI | LLM client | solid | Leaf ids, question, excerpts |
| LLM client | LLM :8003 | solid | `POST /chat`, temperature 0. This is the arrow into the model |
| LLM :8003 | LLM client | dashed | JSON `title`, `outcome`, `assumptions` |
| Simulator FastAPI | RAG client | solid | Only when client variables do not cover the detected families |
| RAG client | RAG :8002 | solid | `GET /search` with `user_id` |
| RAG :8002 | RAG client | dashed | Excerpts, or an empty hit list |
| Simulator FastAPI | Repository | solid | Upsert after the LLM JSON is valid |
| Repository | MongoDB | solid | `simulations` (`user_id`, unique `correlation_id`) |
| Agents :8006 | Simulator | solid | MCP `POST /mcp/tools/simulate_whatif` → `POST /simulate` |
| Simulator | Agents | dashed | Scenarios, or **502** / **504** |

There is **no** arrow from the client into Simulator :8007. There is **no**
arrow from `reason_graph` into the simulator (chat does not auto-route).
There is **no** arrow into Chroma, model weights, or Kafka. The red box is
a prohibition note; it has no edges.

## Arrow direction (`simulator-dataflow.drawio`)

### Flow 1 — premium simulate

Arrowheads move left to right until step 8. The **200** dashed arrow then
runs back along the top and ends on the client.

1. Client → API Router `POST /api/simulate`.
2. Router → Simulator (premium, under 10/min, `X-Request-ID`).
3. Correlation diamond. **Miss** continues right into hydrate. **Hit** is a
   dashed arrow back to the client (skip hydrate, tree, and LLM).
4. Hydrate → RAG :8002 `GET /search` (arrowhead on RAG). Excerpts or an
   empty list come back dashed (arrowhead on hydrate). Covered variables
   skip that pair and continue to the tree.
5. Hydrate → decision tree.
6. Tree → LLM :8003 `POST /chat` temperature 0 (arrowhead on the LLM step).
7. Valid JSON → MongoDB upsert.
8. Persist → **200**. Dashed **200** returns to the client. A separate
   dashed red arrow from step 8 ends on **NO Kafka** (arrowhead on the red
   box). There is no Kafka shape.

### Flow 2 — list and get

1. Client → Router `GET /api/simulations` or `GET /api/simulations/{id}`.
2. Router → Simulator, filtered by the token `user_id`.
3. Simulator → **200** own rows. Dashed **200** returns to the client.
4. Router → red **403** when the caller is free (arrowhead on the red box;
   the arrow does not continue to Simulator).
5. Simulator → red **404** for a cross-user id (arrowhead on the red box).

### Flow 3 — MCP

1. `POST /mcp/tools/simulate_whatif` → Agents :8006.
2. Agents → Simulator `POST /simulate` (same `X-Request-ID`). Arrowhead on Simulator.
3. Simulator → result bubble, dashed (scenarios or 502/504).
4. Result → tool caller, dashed. Arrowhead on step 1.
5. Agents → red **404** for an unknown tool name.
6. Simulator → red **502** / **504** when the downstream call fails. The
   tool does not invent scenarios.
7. `reason_graph` has **one** outgoing arrow, into the red “no auto-route”
   box. It does not point at Simulator.

### Errors

Every red box has exactly one incoming arrow, from the step that produces
it, and no outgoing arrow.

| From | To | Meaning |
|------|----|---------|
| Router (step 2) | No JWT | **401**. No Simulator call |
| Router (step 2) | Free tier | **403**. No Simulator call |
| Router (step 2) | 11th request in the minute | **429**. No Simulator call |
| Correlation check (step 3) | Blank question | **422**. No LLM, no persist |
| Hydrate (step 4) | RAG 5xx / timeout | **502** / **504**. No persist |
| LLM step (step 6) | LLM 5xx, timeout, or bad JSON after one retry | **502** / **504**. No persist |
| HTTP 200 (step 8) | NO Kafka | Simulate does not publish `session.turn.completed` |
| List router | Free GET | **403** |
| List simulator | Cross-user id | **404** |
| Agents MCP | Unknown tool | **404** |
| MCP simulator call | Simulator down | **502** / **504** |
| `reason_graph` | NO auto-route | Chat does not call `simulate_whatif` |

## Color scheme

- Blue (`#dae8fc` / `#6c8ebf`): client, API Router, RAG, LLM, Agents
- Green (`#d5e8d4` / `#82b366`): Simulator Service, tree, clients, 200
- Yellow (`#fff2cc` / `#d6b656`): correlation check, pattern notes, legend
- Gray (`#f5f5f5` / `#666666`): MongoDB `simulations`
- Red (`#f8cecc` / `#b85450`): 401, 403, 404, 422, 429, 502, 504, no Kafka, no auto-route

## How to open

Draw.io desktop, [app.diagrams.net](https://app.diagrams.net), or the VS Code Draw.io extension.

## References

- [Frame 1.1 API Router](../../objective-1-1-api-router/output/diagrams/)
- [Frame 3 RAG](../../objective-3-hybrid-store-rag/output/diagrams/)
- [Frame 5 Agents](../../objective-5-symbiotic-learning/output/diagrams/)
