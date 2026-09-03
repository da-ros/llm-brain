## Purpose

The agents-service capability is the symbiotic learning loop: three MCP agents
(Ingestor, Razonador, Evaluador) orchestrated with LangGraph state graphs. They
ingest premium-user interactions, reason with RAG and the cloud LLM while recording
assumptions, write session feedback, and prepare weekly fine-tune batches that a
human must trigger.

## ADDED Requirements

### Requirement: Agents service health endpoint

The Agents Service SHALL expose an unauthenticated health endpoint that reports
liveness without secrets.

#### Scenario: Service is running

- **GIVEN** the Agents Service process is up
- **WHEN** a client sends `GET /health`
- **THEN** the system responds HTTP 200 with `status` equal to `"ok"`, `service` equal to `"agents-service"`, and `orchestrator` equal to `"langgraph"`

### Requirement: Correlation ID propagation

The Agents Service SHALL propagate `X-Request-ID` on every inbound HTTP request
and every outbound call to RAG, LLM, and Fine-Tune services, and SHALL include
that id in structured logs.

#### Scenario: Inbound header present

- **GIVEN** a request includes `X-Request-ID`
- **WHEN** the Agents Service handles the request
- **THEN** the same id is sent on outbound HTTP headers and appears in every log line for that request

#### Scenario: Inbound header missing

- **GIVEN** a request has no `X-Request-ID`
- **WHEN** the Agents Service handles the request
- **THEN** the service generates a UUID, uses it for the rest of the hop, and returns it on the response

### Requirement: Premium-only access to agents

The symbiotic loop SHALL run only for authenticated premium users. Free-tier users
SHALL NOT have interactions ingested, reasoned with personal context, or added to
fine-tune batches.

#### Scenario: Premium user is accepted

- **GIVEN** the caller is an authenticated user with `subscription_tier` equal to `"premium"`
- **WHEN** a reason or ingest request is received
- **THEN** the Agents Service processes the request for that `user_id` only

#### Scenario: Free user is rejected

- **GIVEN** the caller has `subscription_tier` equal to `"free"`
- **WHEN** a reason or ingest request is received
- **THEN** the Agents Service responds HTTP 403 and does not write interactions, feedback, or batches

### Requirement: Per-user isolation of agent data

Every interaction, feedback record, and fine-tune batch SHALL be stored with
`user_id` and SHALL be readable only by that user (or an administrator triggering
that user's batch).

#### Scenario: User reads own records

- **GIVEN** an authenticated premium user
- **WHEN** they list interactions or batches
- **THEN** the system returns only documents whose `user_id` matches the token

#### Scenario: Cross-user access is denied

- **GIVEN** an authenticated premium user
- **WHEN** they request another user's session, feedback, or batch by id
- **THEN** the system responds HTTP 404 without revealing that the resource exists

### Requirement: Razonador reasons with RAG context and records assumptions

On each premium reason request the Razonador agent SHALL retrieve Top-k personal
context, call the cloud LLM, and return the answer together with an explicit list
of assumptions used.

#### Scenario: Successful reason with context

- **GIVEN** a premium user with indexed documents
- **WHEN** `POST /reason` is called with a user message
- **THEN** the system returns HTTP 200 with `response` (non-empty), `assumptions` (at least one item), `sources`, and `tokens_used`, within the 30 second chat timeout

#### Scenario: RAG has no hits

- **GIVEN** a premium user with no matching documents
- **WHEN** `POST /reason` is called
- **THEN** the system still returns an LLM answer, `assumptions` includes a statement that no personal context was found, and `sources` is empty

#### Scenario: Downstream LLM failure

- **GIVEN** the LLM Service returns 5xx or times out
- **WHEN** `POST /reason` is called
- **THEN** the Agents Service responds HTTP 502 or 504, does not persist a successful interaction, and logs the correlation id

### Requirement: Loop is orchestrated as LangGraph state graphs

The Agents Service SHALL run premium reasoning on a compiled `reason_graph` and
post-turn learning on a compiled `learn_graph`. Graph nodes SHALL call RAG, LLM,
and Fine-Tune over HTTP (no direct Bedrock or vector-store access from this service).

#### Scenario: Reason graph on chat

- **GIVEN** a premium `POST /reason` request
- **WHEN** the service handles it
- **THEN** `reason_graph` runs retrieve → generate → extract_assumptions (or error END on LLM failure) and the HTTP response reflects that graph result

#### Scenario: Learn graph after Kafka

- **GIVEN** a `session.turn.completed` message
- **WHEN** the consumer handles it
- **THEN** `learn_graph` runs ingest → evaluate → maybe_append_batch and Fine-Tune `POST /train` is not invoked

#### Scenario: Health reports graphs

- **GIVEN** the Agents Service is running
- **WHEN** a client sends `GET /health`
- **THEN** the JSON includes an `orchestrator` field equal to `"langgraph"`

### Requirement: Ingestor persists each completed chat turn

After a successful premium reason turn the Ingestor agent SHALL persist the
query, response, assumptions, sources, `session_id`, `user_id`, timestamp, and
correlation id.

#### Scenario: Ingest after successful turn

- **GIVEN** Razonador returned a successful answer
- **WHEN** the Kafka message `session.turn.completed` is consumed
- **THEN** MongoDB contains one `agent_interactions` document for that correlation id and `user_id`

#### Scenario: Duplicate turn is idempotent

- **GIVEN** an interaction for a correlation id already exists
- **WHEN** the same `session.turn.completed` message is consumed again
- **THEN** the system does not insert a second document for that correlation id

### Requirement: Evaluador writes session feedback

The Evaluador agent SHALL score each ingested turn (relevance, completeness) and
persist feedback. It SHALL NOT start a Fine-Tune job.

#### Scenario: Feedback written after ingest

- **GIVEN** a newly ingested interaction
- **WHEN** Evaluador processes that turn
- **THEN** MongoDB contains an `agent_feedback` document with `score`, `reason`, `should_include_in_batch`, `user_id`, and `correlation_id`

#### Scenario: Evaluador never auto-trains

- **GIVEN** any number of feedback records, including scores below a quality threshold
- **WHEN** Evaluador finishes processing
- **THEN** Fine-Tune Service `POST /train` is not called

### Requirement: Weekly fine-tune batch is prepared, not executed

Evaluador SHALL accumulate eligible interactions into a per-user weekly batch
with status `ready`. Training SHALL start only after an authenticated manual
trigger that sends that batch to Fine-Tune Service.

#### Scenario: Eligible sample is appended

- **GIVEN** Evaluador marked `should_include_in_batch` true
- **WHEN** the weekly batch for that user is updated
- **THEN** the interaction id is present in `finetune_batches.items` and `status` is `ready` or `accumulating`

#### Scenario: Manual trigger submits training

- **GIVEN** a batch with status `ready` for the authenticated premium user
- **WHEN** `POST /batches/{batch_id}/trigger` is called
- **THEN** the Agents Service calls Fine-Tune Service `POST /train` with that user's dataset path, sets batch status to `submitted`, and returns the Fine-Tune `job_id`

#### Scenario: Trigger of empty or non-ready batch is rejected

- **GIVEN** a batch that is empty or not `ready`
- **WHEN** a trigger is requested
- **THEN** the system responds HTTP 409 and does not call Fine-Tune Service

### Requirement: MCP tool contracts

Each agent SHALL expose a named tool contract (name, description, input schema)
backed by the corresponding LangGraph node or graph. The host SHALL invoke
Ingestor, Razonador, and Evaluador through those tools without hard-coding
another agent's internals.

#### Scenario: Host lists tools

- **GIVEN** the Agents Service is running
- **WHEN** `GET /mcp/tools` is called
- **THEN** the response lists at least `ingest_turn`, `reason`, and `evaluate_turn`

#### Scenario: Unknown tool is rejected

- **GIVEN** a tool name that is not registered
- **WHEN** `POST /mcp/tools/{name}` is called
- **THEN** the system responds HTTP 404
