## ADDED Requirements

### Requirement: MCP tool scan_message wraps Shield HTTP

The Agents Service SHALL register an MCP tool named `scan_message` that
wraps the Shield Service over HTTP. LangGraph nodes and
`POST /mcp/tools/{name}` SHALL invoke it without accessing Chroma or the
heuristic internals. The Frame 5 `reason_graph` and `learn_graph` SHALL
keep their existing node sequences; premium chat SHALL NOT auto-scan every
turn.

#### Scenario: Host lists the new tool

- **GIVEN** the Agents Service is running with Shield configured
- **WHEN** `GET /mcp/tools` is called
- **THEN** the response lists `scan_message` in addition to the Frame 5 tools and any Frame 6/7 tools already registered

#### Scenario: Tool invocation reaches Shield

- **GIVEN** a premium `user_id` and message payload
- **WHEN** `POST /mcp/tools/scan_message` is called
- **THEN** Agents Service forwards HTTP to Shield Service `POST /scan` with the same `X-Request-ID` and returns `alert`, `severity`, and `reasons`

#### Scenario: Shield downstream failure

- **GIVEN** the Shield Service returns 5xx or times out
- **WHEN** `POST /mcp/tools/scan_message` is called
- **THEN** the Agents Service responds HTTP 502 or 504, does not invent an alert, and logs the correlation id

## MODIFIED Requirements

### Requirement: MCP tool contracts

The Agents Service SHALL implement its own MCP tool contracts (name, description,
input schema), each wrapping one internal service over HTTP and invoked by the
LangGraph nodes: `rag_search` (RAG 8002), `llm_generate` (LLM 8003), `ingest_turn`
(MongoDB `agent_interactions`), `evaluate_turn` (MongoDB `agent_feedback`,
`finetune_batches`), `finetune_trigger` (Fine-Tune 8004, manual only),
`simulate_whatif` (Simulator 8007, when Frame 6 is deployed),
`analytics_query` (Analytics 8008, when Frame 7 is deployed), and
`scan_message` (Shield 8009). The host SHALL invoke Ingestor, Razonador,
and Evaluador through those tools without hard-coding another agent's internals,
and SHALL NOT integrate third-party MCP servers.

#### Scenario: Host lists tools

- **GIVEN** the Agents Service is running with Shield configured
- **WHEN** `GET /mcp/tools` is called
- **THEN** the response lists at least `rag_search`, `llm_generate`, `ingest_turn`, `evaluate_turn`, `finetune_trigger`, and `scan_message`

#### Scenario: Unknown tool is rejected

- **GIVEN** a tool name that is not registered
- **WHEN** `POST /mcp/tools/{name}` is called
- **THEN** the system responds HTTP 404
