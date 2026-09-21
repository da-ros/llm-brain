## ADDED Requirements

### Requirement: Premium shield scan endpoint

The API Router SHALL accept an authenticated premium scan of pasted text,
an image, or a short video, forward it to the Shield Service over HTTP
sync, and return the alert payload including `llm_used`. It SHALL NOT
publish Kafka events for scans. Clients SHALL NOT call port 8009.

#### Scenario: Premium user scans text, an image, or a video

- **GIVEN** an authenticated premium user
- **WHEN** they send `POST /api/shield/scan` with text and/or an image or video file and a valid `source`
- **THEN** the Router calls Shield Service `POST /scan` with `X-Request-ID`, returns HTTP 200 with `alert`, `likelihood`, and `reasons`, and does not publish Kafka

#### Scenario: Free user cannot scan

- **GIVEN** an authenticated free-tier user
- **WHEN** they send `POST /api/shield/scan`
- **THEN** the Router responds HTTP 403 and does not call Shield Service

#### Scenario: Unauthenticated scan is rejected

- **GIVEN** a request without a valid JWT
- **WHEN** `POST /api/shield/scan` is called
- **THEN** the Router responds HTTP 401 and does not call Shield Service

#### Scenario: Scan rate limit

- **GIVEN** an authenticated premium user who already sent 30 scan requests in the current minute
- **WHEN** they send another `POST /api/shield/scan`
- **THEN** the Router responds HTTP 429 and does not call Shield Service

### Requirement: Premium incidents list matches Frame 7 contract

The API Router SHALL expose `GET /api/shield/incidents` for the token
`user_id`. The JSON SHALL be `{ incidents: [{ id, created_at, severity, summary, source }] }`.
An empty list SHALL be HTTP 200, not 404.

#### Scenario: Premium user lists incidents

- **GIVEN** an authenticated premium user with stored alerts
- **WHEN** they send `GET /api/shield/incidents`
- **THEN** the Router returns HTTP 200 with only that user's `incidents` array in the Frame 7 shape

#### Scenario: No incidents yet

- **GIVEN** an authenticated premium user with no alerts
- **WHEN** they send `GET /api/shield/incidents`
- **THEN** the Router returns HTTP 200 with `incidents` equal to `[]`

#### Scenario: Free user cannot list incidents

- **GIVEN** an authenticated free-tier user
- **WHEN** they send `GET /api/shield/incidents`
- **THEN** the Router responds HTTP 403

### Requirement: Responsible-use guidelines endpoint

The API Router SHALL proxy `GET /api/shield/guidelines` for authenticated
premium users.

#### Scenario: Premium user reads guidelines

- **GIVEN** an authenticated premium user
- **WHEN** they send `GET /api/shield/guidelines`
- **THEN** the Router returns HTTP 200 with English `text` and no secrets

## MODIFIED Requirements

### Requirement: Health check endpoint (from platform-foundation)

The health check endpoint SHALL remain public and include service information.
The response SHALL include the service name `"api-gateway"` and version.

#### Scenario: Public health

- **GIVEN** the API Router is running
- **WHEN** a client sends `GET /health`
- **THEN** the Router responds HTTP 200 without JWT
