# Architecture Diagrams — llm-brain (Frame 1)

Draw.io XML for the AI-Augmented Digital Brain local MVP. This is the only copy.

## Files

| File | C4 level | Description |
|------|----------|-------------|
| `c4-context.drawio` | Level 1 | Actors, llm-brain, on-device Qwen3.5-4B via llama.rn, host Qwen process on port 8003, MongoDB, Chroma. AWS API Gateway shown as future. |
| `c4-container.drawio` | Level 2 | Web / React Native, API Router, Kafka, ETL/RAG/LLM/Fine-Tune/Agents, local stores |
| `c4-component-api.drawio` | Level 3 | `services/api-router`: FastAPI, config, JWT, `LLMProvider` protocol, `OnDeviceProvider`, `QwenLocalProvider` (nombre legacy — la capa de providers vive en `services/llm/providers/`, ramas por `LLM_BACKEND`) |
| `deployment.drawio` | — | Local MVP. Ports 8003 and 8004 are labeled host processes. AWS ECS Fargate is dashed and out of scope |
| `mcp-agent-flow.drawio` | — | Ingestor / Razonador / Evaluador MCP loop (Premium) |

## Open

Draw.io Desktop, [app.diagrams.net](https://app.diagrams.net), or the VS Code Draw.io Integration extension.

## Color scheme

Legend at the bottom of each diagram uses a colored dot (not the color name):

- Blue `#dae8fc` — clients
- Yellow `#fff2cc` — API / config / auth
- Green `#d5e8d4` — LLM and microservices
- Purple `#e1d5e7` (dashed) — AWS future
- Red `#f8cecc` — Kafka / Fine-Tune
- Gray `#f5f5f5` — local data stores
