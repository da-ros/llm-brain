## ADDED Requirements

### Requirement: Premium chat is routed through Razonador

For premium users, `POST /api/chat` SHALL call the Agents Service Razonador
(not RAG and LLM directly). The HTTP response SHALL include the answer and the
explicit assumptions. After returning, the Router SHALL publish
`session.turn.completed` to Kafka.

#### Scenario: Premium chat uses Razonador

- **GIVEN** an authenticated premium user
- **WHEN** they send `POST /api/chat` with a message
- **THEN** the Router calls Agents Service `POST /reason`, returns HTTP 200 with `response` and `assumptions`, and publishes Kafka `session.turn.completed` with the same `X-Request-ID`

#### Scenario: Free chat does not use agents

- **GIVEN** an authenticated free-tier user
- **WHEN** they send `POST /api/chat`
- **THEN** the Router does not call Agents Service, does not publish `session.turn.completed`, and does not inject RAG context

#### Scenario: Unauthenticated chat is rejected

- **GIVEN** a request without a valid JWT
- **WHEN** `POST /api/chat` is called
- **THEN** the Router responds HTTP 401 and does not call Agents Service

### Requirement: Session end endpoint

The API Router SHALL accept an authenticated premium request to end a chat
session so Evaluador can finalize feedback for that `session_id`.

#### Scenario: Premium user ends session

- **GIVEN** an authenticated premium user with an open `session_id`
- **WHEN** they send `POST /api/sessions/end` with that `session_id`
- **THEN** the Router publishes a session-end event (or calls Agents Service) with `X-Request-ID` and returns HTTP 202

#### Scenario: Free user cannot end an agent session

- **GIVEN** an authenticated free-tier user
- **WHEN** they send `POST /api/sessions/end`
- **THEN** the Router responds HTTP 403

### Requirement: Manual fine-tune trigger from the Router

The API Router SHALL expose an authenticated premium endpoint that forwards a
ready Evaluador batch to Fine-Tune Service. It SHALL NOT start training unless
the user (or administrator) explicitly calls this endpoint.

#### Scenario: Manual trigger of a ready batch

- **GIVEN** an authenticated premium user with a `ready` batch
- **WHEN** they send `POST /api/finetune` with `batch_id`
- **THEN** the Router forwards to Agents Service trigger (or Fine-Tune `POST /train`), returns HTTP 202 with `job_id`, and does not start a second job for the same batch

#### Scenario: Missing batch_id

- **GIVEN** an authenticated premium user
- **WHEN** they send `POST /api/finetune` without `batch_id`
- **THEN** the Router responds HTTP 422

## MODIFIED Requirements

### Requirement: Health check endpoint (from platform-foundation)

The health check endpoint SHALL remain public and include service information.
The response SHALL include the service name `"api-gateway"` and version.

#### Scenario: Public health

- **GIVEN** the API Router is running
- **WHEN** a client sends `GET /health`
- **THEN** the Router responds HTTP 200 without JWT
