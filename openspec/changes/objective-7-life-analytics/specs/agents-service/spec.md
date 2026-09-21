## ADDED Requirements

### Requirement: MCP tool analytics_query wraps Analytics HTTP

The Agents Service SHALL register an MCP tool named `analytics_query` that
wraps the Analytics Service over HTTP. LangGraph nodes and
`POST /mcp/tools/{name}` SHALL invoke it without accessing Chroma or MongoDB
directly. The Frame 5 `reason_graph` and `learn_graph` SHALL keep their
existing node sequences.

#### Scenario: Host lists the new tool

- **GIVEN** the Agents Service is running with Analytics configured
- **WHEN** `GET /mcp/tools` is called
- **THEN** the response lists `analytics_query` in addition to the Frame 5 tools and `simulate_whatif` when that tool is registered

#### Scenario: Tool invocation reaches Analytics

- **GIVEN** a premium `user_id`
- **WHEN** `POST /mcp/tools/analytics_query` is called
- **THEN** Agents Service forwards HTTP to Analytics Service `GET /correlations` with the same `X-Request-ID` and returns both correlation pairs

#### Scenario: Analytics downstream failure

- **GIVEN** the Analytics Service returns 5xx or times out
- **WHEN** `POST /mcp/tools/analytics_query` is called
- **THEN** the Agents Service responds HTTP 502 or 504, does not invent `r` values, and logs the correlation id

## MODIFIED Requirements

### Requirement: MCP tool contracts

The Agents Service SHALL implement its own MCP tool contracts (name, description,
input schema), each wrapping one internal service over HTTP and invoked by the
LangGraph nodes: `rag_search` (RAG 8002), `llm_generate` (LLM 8003), `ingest_turn`
(MongoDB `agent_interactions`), `evaluate_turn` (MongoDB `agent_feedback`,
`finetune_batches`), `finetune_trigger` (Fine-Tune 8004, manual only),
`simulate_whatif` (Simulator 8007, when Frame 6 is deployed), and
`analytics_query` (Analytics 8008). The host SHALL invoke Ingestor, Razonador,
and Evaluador through those tools without hard-coding another agent's internals,
and SHALL NOT integrate third-party MCP servers.

#### Scenario: Host lists tools

- **GIVEN** the Agents Service is running with Analytics configured
- **WHEN** `GET /mcp/tools` is called
- **THEN** the response lists at least `rag_search`, `llm_generate`, `ingest_turn`, `evaluate_turn`, `finetune_trigger`, and `analytics_query`

#### Scenario: Unknown tool is rejected

- **GIVEN** a tool name that is not registered
- **WHEN** `POST /mcp/tools/{name}` is called
- **THEN** the system responds HTTP 404
