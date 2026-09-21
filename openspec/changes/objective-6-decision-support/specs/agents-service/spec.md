## ADDED Requirements

### Requirement: MCP tool simulate_whatif wraps Simulator HTTP

The Agents Service SHALL register an MCP tool named `simulate_whatif` that
wraps the Simulator Service over HTTP. LangGraph nodes and `POST /mcp/tools/{name}`
SHALL invoke it without accessing Chroma, the LLM weights, or the simulator
tree internals. The Frame 5 `reason_graph` and `learn_graph` SHALL keep their
existing node sequences; premium chat SHALL NOT auto-route what-if questions
to the simulator.

#### Scenario: Host lists the new tool

- **GIVEN** the Agents Service is running with Simulator configured
- **WHEN** `GET /mcp/tools` is called
- **THEN** the response lists `simulate_whatif` in addition to `rag_search`, `llm_generate`, `ingest_turn`, `evaluate_turn`, and `finetune_trigger`

#### Scenario: Tool invocation reaches Simulator

- **GIVEN** a premium `user_id` and a what-if payload
- **WHEN** `POST /mcp/tools/simulate_whatif` is called
- **THEN** Agents Service forwards HTTP to Simulator Service with the same `X-Request-ID` and returns the simulator scenarios

#### Scenario: Simulator downstream failure

- **GIVEN** the Simulator Service returns 5xx or times out
- **WHEN** `POST /mcp/tools/simulate_whatif` is called
- **THEN** the Agents Service responds HTTP 502 or 504, does not invent scenarios, and logs the correlation id

## MODIFIED Requirements

### Requirement: MCP tool contracts

The Agents Service SHALL implement its own MCP tool contracts (name, description,
input schema), each wrapping one internal service over HTTP and invoked by the
LangGraph nodes: `rag_search` (RAG 8002), `llm_generate` (LLM 8003), `ingest_turn`
(MongoDB `agent_interactions`), `evaluate_turn` (MongoDB `agent_feedback`,
`finetune_batches`), `finetune_trigger` (Fine-Tune 8004, manual only), and
`simulate_whatif` (Simulator 8007). The host SHALL invoke Ingestor, Razonador,
and Evaluador through those tools without hard-coding another agent's internals,
and SHALL NOT integrate third-party MCP servers.

#### Scenario: Host lists tools

- **GIVEN** the Agents Service is running
- **WHEN** `GET /mcp/tools` is called
- **THEN** the response lists at least `rag_search`, `llm_generate`, `ingest_turn`, `evaluate_turn`, `finetune_trigger`, and `simulate_whatif`

#### Scenario: Unknown tool is rejected

- **GIVEN** a tool name that is not registered
- **WHEN** `POST /mcp/tools/{name}` is called
- **THEN** the system responds HTTP 404
