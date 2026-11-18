## Purpose

> **Current runtime.** This file keeps the decision text of this frame. Before citing it as the running system, read `docs/architecture/current-runtime.md`.


The platform-foundation capability provides the shared application entry point for the digital
brain: configuration loading, a health probe, JWT-based authentication with user registration,
per-user data isolation, and model-agnostic resolution of the active LLM provider, so every
later module builds on one consistent contract.

## ADDED Requirements

### Requirement: Health check endpoint

The system SHALL expose an unauthenticated `GET /health` endpoint that reports service liveness
and the resolved LLM provider name without exposing secrets.

#### Scenario: Service is running

- **WHEN** a client sends `GET /health`
- **THEN** the system responds with HTTP 200 and a JSON body containing a `status` field equal to
  `"ok"` and an `llm_provider` field naming the currently configured provider

#### Scenario: Secrets are never exposed

- **WHEN** a client sends `GET /health`
- **THEN** the response body does NOT contain any API key, password, or connection string

### Requirement: Environment-based configuration

The system SHALL load its configuration from environment variables (with `.env` support) and
SHALL start with documented safe defaults when optional variables are absent.

#### Scenario: Missing optional configuration falls back to defaults

- **WHEN** the service starts without optional variables set (e.g. `API_PORT`)
- **THEN** the service starts successfully using the documented default values

#### Scenario: Required secret is absent

- **WHEN** the selected LLM provider requires an API key and that key is not configured
- **THEN** the system reports a clear configuration error naming the missing variable and does
  NOT start serving LLM-backed requests

### Requirement: Model-agnostic LLM provider resolution

The system SHALL select the active LLM provider and model from configuration at runtime, and
SHALL support at least an on-device provider (Qwen3.5-4B quantized in React Native on iPhone
via Neural Engine / Metal — Free uses the **base** model; Premium uses the **fine-tuned**
build) and a "cloud" provider served by the LLM Service on port 8003 — a **host process**
(Qwen3.5-4B **base**, not fine-tuned, for Premium + RAG; runtime chosen with `LLM_BACKEND`:
`qwen_local` | `ollama`)
without code changes to switch between them.

#### Scenario: Switching provider via configuration

- **WHEN** the `LLM_PROVIDER` value changes between a supported local and a supported cloud
  provider and the service restarts
- **THEN** subsequent LLM requests are routed to the newly selected provider without any code
  modification

#### Scenario: Unsupported provider is rejected

- **WHEN** `LLM_PROVIDER` is set to a value that is not supported
- **THEN** the system fails fast at startup with an error listing the supported providers

### Requirement: User registration

The system SHALL allow new users to create an account with email and password. Passwords
SHALL be hashed with bcrypt before storage. Each user receives a unique `user_id` that
serves as the isolation boundary for all personal data.

#### Scenario: Successful registration

- **WHEN** a client sends `POST /auth/register` with a valid email and password
- **THEN** the system creates a new user record with a bcrypt-hashed password and returns
  HTTP 201 with the user ID (no secrets leaked)

#### Scenario: Duplicate email

- **WHEN** a client sends `POST /auth/register` with an email that already exists
- **THEN** the system responds with HTTP 409 Conflict

### Requirement: JWT authentication for protected endpoints

The system SHALL protect non-public endpoints with JWT bearer tokens, while keeping
`GET /health` public. Tokens SHALL be issued upon successful login and validated on
each request via a FastAPI dependency.

#### Scenario: Successful login

- **WHEN** a client sends `POST /auth/login` with valid email and password
- **THEN** the system returns a signed JWT token containing the `user_id` and `subscription_tier`

#### Scenario: Missing or invalid token

- **WHEN** a client calls a protected endpoint without a valid JWT token
- **THEN** the system responds with HTTP 401 and does not perform the requested action

#### Scenario: Expired token

- **WHEN** a client calls a protected endpoint with an expired JWT token
- **THEN** the system responds with HTTP 401 with an error indicating token expiration

### Requirement: Per-user data isolation

The system SHALL isolate all user data (documents, embeddings, subscriptions) by `user_id`.
No user SHALL be able to access, modify, or delete another user's data through any API
endpoint. All data queries SHALL include a `user_id` filter.

#### Scenario: Cross-user access attempt

- **WHEN** an authenticated user sends a request targeting another user's document ID
- **THEN** the system responds with HTTP 403 Forbidden or HTTP 404 Not Found (never revealing
  the existence of the other user's data)

#### Scenario: User-scoped data listing

- **WHEN** an authenticated user requests their documents
- **THEN** the system returns only documents belonging to that user's `user_id`
