## Purpose

The simulator-service capability is the premium Decision-Support Simulator:
a what-if engine that turns a question plus key personal variables into 3–5
scenarios. A decision tree chooses the leaves; Qwen3.5-4B reasons about
each one and writes explicit assumptions. Runs are persisted per user.

## ADDED Requirements

### Requirement: Simulator service health endpoint

The Simulator Service SHALL expose an unauthenticated health endpoint that
reports liveness without secrets.

#### Scenario: Service is running

- **GIVEN** the Simulator Service process is up
- **WHEN** a client sends `GET /health`
- **THEN** the system responds HTTP 200 with `status` equal to `"ok"` and `service` equal to `"simulator-service"`

### Requirement: Correlation ID propagation

The Simulator Service SHALL propagate `X-Request-ID` on every inbound HTTP
request and every outbound call to RAG and the LLM Service, and SHALL
include that id in structured logs.

#### Scenario: Inbound header present

- **GIVEN** a request includes `X-Request-ID`
- **WHEN** the Simulator Service handles the request
- **THEN** the same id is sent on outbound RAG headers and appears in every log line for that request

#### Scenario: Inbound header missing

- **GIVEN** a request has no `X-Request-ID`
- **WHEN** the Simulator Service handles the request
- **THEN** the service generates a UUID, uses it for the rest of the hop, and returns it on the response

### Requirement: Premium-only access to simulations

The simulator SHALL run only for authenticated premium users. Free-tier
users SHALL NOT obtain scenarios or persist simulations.

#### Scenario: Premium user is accepted

- **GIVEN** the caller is an authenticated user with `subscription_tier` equal to `"premium"`
- **WHEN** a simulate request is received
- **THEN** the Simulator Service processes the request for that `user_id` only

#### Scenario: Free user is rejected

- **GIVEN** the caller has `subscription_tier` equal to `"free"`
- **WHEN** a simulate request is received
- **THEN** the Simulator Service responds HTTP 403 and does not write a `simulations` document

### Requirement: What-if produces 3-5 traced scenarios reasoned by the LLM

On each new simulate request the Simulator Service SHALL walk a decision
tree and return between three and five scenarios. Each scenario SHALL
include a title, an outcome, a non-empty `assumptions` list, and a `trace`
of tree nodes visited. The outcome and assumptions SHALL come from one
call to the LLM Service (`POST /chat`, Qwen3.5-4B base, temperature 0)
that is given the question, the variables, the RAG excerpts, and the leaf
ids. The service SHALL NOT use random sampling or Monte Carlo and SHALL
NOT treat a template-only result as success.

#### Scenario: Successful simulate with supplied variables

- **GIVEN** a premium user and a what-if `question` with numeric `variables`
- **WHEN** `POST /simulate` is called
- **THEN** the system calls the LLM Service once, responds HTTP 200 within 30 seconds with `llm_used` equal to true and `scenario_count` between 3 and 5 inclusive, and every scenario has `title`, `outcome`, `assumptions` (at least one item), and `trace` (at least one node id)

#### Scenario: Same inputs select the same leaves

- **GIVEN** the same `user_id`, `question`, `variables`, and RAG snapshot and two different correlation ids
- **WHEN** `POST /simulate` is called twice
- **THEN** both responses contain the same ordered `trace` node ids and both record that the LLM was called

#### Scenario: LLM failure does not persist a simulation

- **GIVEN** the LLM Service returns 5xx, times out, or returns JSON that is still invalid after one retry
- **WHEN** `POST /simulate` is called
- **THEN** the Simulator Service responds HTTP 502 or 504, does not persist a simulation, and logs the correlation id

#### Scenario: Empty question is rejected

- **GIVEN** a premium user
- **WHEN** `POST /simulate` is called with a missing or blank `question`
- **THEN** the system responds HTTP 422, does not call the LLM Service, and does not persist a simulation

### Requirement: Missing variables are hydrated from RAG with explicit defaults

When the request omits a key variable the Simulator Service SHALL retrieve
Top-k personal context via RAG HTTP scoped to `user_id`. Heuristic parsing
MAY fill sleep hours, meeting load, expenses, or medication mentions from
retrieved text. Any default or missing fact SHALL appear as an assumption
in every scenario that uses it. The service SHALL NOT read Chroma or
GridFS directly.

#### Scenario: RAG supplies a missing variable

- **GIVEN** a premium user with indexed documents that mention sleep duration and the request omits `sleep_hours`
- **WHEN** `POST /simulate` is called
- **THEN** the engine uses a value parsed from RAG context and `sources` is non-empty

#### Scenario: RAG has no matching facts

- **GIVEN** a premium user with no matching documents and omitted variables
- **WHEN** `POST /simulate` is called
- **THEN** the system still returns 3–5 scenarios, `assumptions` include a statement that no personal context was found for the missing variable and a default was used, and `sources` is empty

#### Scenario: Downstream RAG failure

- **GIVEN** the RAG Service returns 5xx or times out
- **WHEN** `POST /simulate` is called without complete variables
- **THEN** the Simulator Service responds HTTP 502 or 504, does not persist a successful simulation, and logs the correlation id

### Requirement: Simulations are persisted and isolated by user

Every successful simulate run SHALL be stored in MongoDB with `user_id`,
`question`, `variables`, `scenarios`, `assumptions`, `sources`, `trace`,
`llm_used`, `correlation_id`, and `created_at`. Reads SHALL return only the
caller's rows. Cross-user access SHALL NOT reveal that a resource exists.

#### Scenario: Successful run is stored

- **GIVEN** a premium simulate request that returns HTTP 200
- **WHEN** the response is sent
- **THEN** MongoDB contains one `simulations` document for that `correlation_id` and `user_id`

#### Scenario: Duplicate correlation id is idempotent

- **GIVEN** a simulation for a correlation id already exists
- **WHEN** the same simulate request is retried with that `X-Request-ID`
- **THEN** the system does not insert a second document and returns the stored scenarios

#### Scenario: User lists own simulations

- **GIVEN** an authenticated premium user with prior runs
- **WHEN** they send `GET /simulations`
- **THEN** the system returns only documents whose `user_id` matches the token

#### Scenario: Cross-user access is denied

- **GIVEN** an authenticated premium user
- **WHEN** they request another user's simulation by id
- **THEN** the system responds HTTP 404 without revealing that the resource exists
