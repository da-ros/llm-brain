## Purpose

The api-router capability provides the central entry point for all client requests
in the microservices architecture. It handles JWT authentication, correlation ID
generation, routing to microservices, Kafka integration for async operations,
and task status polling.

## ADDED Requirements

### Requirement: Correlation ID generation

The API Router SHALL generate a unique correlation ID (UUID) for every incoming request
and propagate it via the X-Request-ID header.

#### Scenario: Request without correlation ID

- **WHEN** a client sends a request without X-Request-ID header
- **THEN** the router generates a new UUID and adds it to the response headers

#### Scenario: Request with correlation ID

- **WHEN** a client sends a request with X-Request-ID header
- **THEN** the router uses the provided correlation ID and propagates it

### Requirement: JWT authentication

The API Router SHALL validate JWT tokens for all protected endpoints.

#### Scenario: Valid token

- **WHEN** a client sends a request with a valid JWT token
- **THEN** the router extracts user_id and subscription_tier from the token

#### Scenario: Invalid or missing token

- **WHEN** a client sends a request without or with invalid JWT token
- **THEN** the router responds with HTTP 401 Unauthorized

#### Scenario: Health endpoint public

- **WHEN** a client sends GET /health
- **THEN** the router responds without requiring JWT authentication

### Requirement: File upload with Kafka async processing

The API Router SHALL accept file uploads and process them asynchronously via Kafka.

#### Scenario: Successful upload

- **WHEN** a premium user uploads a valid file (PDF, HTML, EML, image)
- **THEN** the router saves the file to MongoDB GridFS, publishes to Kafka "file.uploaded", and returns HTTP 202 with correlation_id

#### Scenario: Non-premium user upload

- **WHEN** a free tier user attempts to upload a file
- **THEN** the router responds with HTTP 403 Forbidden

#### Scenario: Invalid file type

- **WHEN** a client uploads a file with unsupported MIME type
- **THEN** the router responds with HTTP 422 Unprocessable Entity

### Requirement: Task status polling

The API Router SHALL provide task status via polling endpoint.

#### Scenario: Task in progress

- **WHEN** a client polls GET /tasks/:correlation_id for a processing task
- **THEN** the router returns {status: "in_progress", retries: 0}

#### Scenario: Task completed

- **WHEN** a client polls GET /tasks/:correlation_id for a completed task
- **THEN** the router returns {status: "success", result: {...}}

#### Scenario: Task failed

- **WHEN** a client polls GET /tasks/:correlation_id for a failed task
- **THEN** the router returns {status: "error", error_message: "..."}

#### Scenario: Task not found

- **WHEN** a client polls GET /tasks/:correlation_id for non-existent task
- **THEN** the router responds with HTTP 404 Not Found

#### Scenario: Task belongs to another user

- **WHEN** a client polls GET /tasks/:correlation_id for another user's task
- **THEN** the router responds with HTTP 403 Forbidden

### Requirement: Kafka consumer for task responses

The API Router SHALL consume task responses from Kafka and update MongoDB.

#### Scenario: Success response

- **WHEN** the router receives a success response from Kafka "task.response"
- **THEN** the router updates task_status to "success" in MongoDB

#### Scenario: Error response with retry

- **WHEN** the router receives a 5xx error response and retries < max_retries
- **THEN** the router increments retries and re-publishes to Kafka

#### Scenario: Error response without retry

- **WHEN** the router receives a 3xx/4xx error response
- **THEN** the router updates task_status to "error" (no retry)

#### Scenario: Max retries reached

- **WHEN** the router receives a 5xx error and retries >= max_retries
- **THEN** the router updates task_status to "dlq-max" (permanent failure)

## MODIFIED Requirements

### Requirement: Health check endpoint (from platform-foundation)

The health check endpoint SHALL remain public and include service information.
The response SHALL include the service name "api-gateway" and version.

#### Scenario: Health check remains public

- **WHEN** a client sends GET /health without authentication
- **THEN** the router responds with HTTP 200 without requiring a JWT token

#### Scenario: Health check includes service information

- **WHEN** a client sends GET /health
- **THEN** the response body includes the service name "api-gateway" and version, and no secrets
