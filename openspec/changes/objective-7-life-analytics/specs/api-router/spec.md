## ADDED Requirements

### Requirement: Premium analytics ingest endpoint

The API Router SHALL accept an authenticated premium diary or schedule file
(CSV, XLSX, DOCX, ICS, or an image), forward it to the Analytics Service over HTTP
sync, and return the ingest result including `llm_used`. It SHALL NOT
publish Kafka events for analytics ingest. Clients SHALL NOT call port
8008. OAuth calendar connectors SHALL NOT be exposed.

#### Scenario: Premium user ingests a diary or schedule

- **GIVEN** an authenticated premium user
- **WHEN** they send `POST /api/analytics/ingest` with a `.csv`, `.xlsx`, `.docx`, `.ics`, or image file
- **THEN** the Router calls Analytics Service `POST /ingest` with `X-Request-ID`, returns HTTP 200 with `rows_upserted` and `llm_used`, and does not publish Kafka

#### Scenario: Free user cannot ingest analytics

- **GIVEN** an authenticated free-tier user
- **WHEN** they send `POST /api/analytics/ingest`
- **THEN** the Router responds HTTP 403 and does not call Analytics Service

#### Scenario: Unauthenticated ingest is rejected

- **GIVEN** a request without a valid JWT
- **WHEN** `POST /api/analytics/ingest` is called
- **THEN** the Router responds HTTP 401 and does not call Analytics Service

#### Scenario: Ingest rate limit

- **GIVEN** an authenticated premium user who already sent 10 analytics ingest requests in the current minute
- **WHEN** they send another `POST /api/analytics/ingest`
- **THEN** the Router responds HTTP 429 and does not call Analytics Service

### Requirement: Premium correlations and metrics endpoints

The API Router SHALL expose authenticated premium endpoints that proxy
Analytics `GET /correlations` and `GET /metrics` for the token `user_id`.

#### Scenario: Premium user reads correlations

- **GIVEN** an authenticated premium user with stored metrics
- **WHEN** they send `GET /api/analytics/correlations`
- **THEN** the Router returns HTTP 200 with both sleep/productivity and meetings/focus pairs (`r`, `n`, `status`, `points`) and the latest LLM `narrative`

#### Scenario: Correlations rate limit

- **GIVEN** an authenticated premium user who already sent 30 correlation requests in the current minute
- **WHEN** they send another `GET /api/analytics/correlations`
- **THEN** the Router responds HTTP 429

#### Scenario: Free user cannot read analytics

- **GIVEN** an authenticated free-tier user
- **WHEN** they send `GET /api/analytics/correlations` or `GET /api/analytics/metrics`
- **THEN** the Router responds HTTP 403

#### Scenario: Cross-user metrics id is hidden

- **GIVEN** an authenticated premium user
- **WHEN** they request another user's analytics resource by id
- **THEN** the Router responds HTTP 404

## MODIFIED Requirements

### Requirement: Health check endpoint (from platform-foundation)

The health check endpoint SHALL remain public and include service information.
The response SHALL include the service name `"api-gateway"` and version.

#### Scenario: Public health

- **GIVEN** the API Router is running
- **WHEN** a client sends `GET /health`
- **THEN** the Router responds HTTP 200 without JWT
