## ADDED Requirements

### Requirement: Premium simulate endpoint

The API Router SHALL accept an authenticated premium what-if request, forward
it to the Simulator Service over HTTP sync, and return the scenarios. It SHALL
NOT publish Kafka events for simulate. Clients SHALL NOT call port 8007.

#### Scenario: Premium user runs a simulation

- **GIVEN** an authenticated premium user
- **WHEN** they send `POST /api/simulate` with a `question`
- **THEN** the Router calls Simulator Service `POST /simulate` with `X-Request-ID`, returns HTTP 200 with `scenarios` (length 3–5) and `assumptions`, and does not publish Kafka `session.turn.completed`

#### Scenario: Free user cannot simulate

- **GIVEN** an authenticated free-tier user
- **WHEN** they send `POST /api/simulate`
- **THEN** the Router responds HTTP 403 and does not call Simulator Service

#### Scenario: Unauthenticated simulate is rejected

- **GIVEN** a request without a valid JWT
- **WHEN** `POST /api/simulate` is called
- **THEN** the Router responds HTTP 401 and does not call Simulator Service

#### Scenario: Simulate rate limit

- **GIVEN** an authenticated premium user who already sent 10 simulate requests in the current minute
- **WHEN** they send another `POST /api/simulate`
- **THEN** the Router responds HTTP 429 and does not call Simulator Service

### Requirement: List and fetch own simulations

The API Router SHALL expose authenticated premium endpoints to list and fetch
simulations belonging to the token `user_id`.

#### Scenario: Premium user lists history

- **GIVEN** an authenticated premium user with stored simulations
- **WHEN** they send `GET /api/simulations`
- **THEN** the Router returns HTTP 200 with only that user's simulations

#### Scenario: Premium user fetches one simulation

- **GIVEN** an authenticated premium user and a simulation id they own
- **WHEN** they send `GET /api/simulations/{id}`
- **THEN** the Router returns HTTP 200 with that simulation including scenarios, assumptions, and trace

#### Scenario: Cross-user fetch is hidden

- **GIVEN** an authenticated premium user
- **WHEN** they send `GET /api/simulations/{id}` for another user's id
- **THEN** the Router responds HTTP 404

#### Scenario: Free user cannot list simulations

- **GIVEN** an authenticated free-tier user
- **WHEN** they send `GET /api/simulations`
- **THEN** the Router responds HTTP 403

## MODIFIED Requirements

### Requirement: Health check endpoint (from platform-foundation)

The health check endpoint SHALL remain public and include service information.
The response SHALL include the service name `"api-gateway"` and version.

#### Scenario: Public health

- **GIVEN** the API Router is running
- **WHEN** a client sends `GET /health`
- **THEN** the Router responds HTTP 200 without JWT
