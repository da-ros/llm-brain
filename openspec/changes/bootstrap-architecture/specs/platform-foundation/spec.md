## Purpose

The platform-foundation capability provides the shared application entry point for the digital
brain: configuration loading, a health probe, basic authentication, and model-agnostic
resolution of the active LLM provider, so every later module builds on one consistent contract.

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
SHALL support at least a local proxy provider (ollama) and a cloud provider (OpenRouter /
OpenAI-compatible) without code changes to switch between them.

#### Scenario: Switching provider via configuration

- **WHEN** the `LLM_PROVIDER` value changes between a supported local and a supported cloud
  provider and the service restarts
- **THEN** subsequent LLM requests are routed to the newly selected provider without any code
  modification

#### Scenario: Unsupported provider is rejected

- **WHEN** `LLM_PROVIDER` is set to a value that is not supported
- **THEN** the system fails fast at startup with an error listing the supported providers

### Requirement: Basic authentication for protected endpoints

The system SHALL protect non-public endpoints with basic authentication, while keeping
`GET /health` public.

#### Scenario: Missing or invalid credentials

- **WHEN** a client calls a protected endpoint without valid credentials
- **THEN** the system responds with HTTP 401 and does not perform the requested action

#### Scenario: Valid credentials

- **WHEN** a client calls a protected endpoint with valid configured credentials
- **THEN** the system authorizes the request and processes it
